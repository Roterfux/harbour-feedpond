# Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
"""What the QML side calls (through PyOtherSide).

Quick calls return their result. Slow ones (subscribe, import_opml, refresh) start a
background job, return True at once (False while another job runs) and report with events:
    busy(on, done, total)   a job runs; total 0 = no count yet
    changed(unread)         stored data changed - reload lists
    notice(text)            one line for the user (result or error)
    full(item_id, result)   the answer to open_full
"""
import hashlib
import http.client
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor

import feedparse
from feedparse import FeedError
from store import Store

try:
    import pyotherside
except ImportError:          # tests on a PC
    pyotherside = None

USER_AGENT = "Feedpond/0.1 (feed reader for Sailfish OS)"
ACCEPT = ("application/atom+xml, application/rss+xml, application/rdf+xml, "
          "application/xml;q=0.9, text/xml;q=0.9, text/html;q=0.7, */*;q=0.5")
# Some sites turn away clients that do not look like a browser
PAGE_AGENT = ("Mozilla/5.0 (Linux; Sailfish OS; Mobile) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Feedpond/0.3")
PAGE_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
FULL_MIN = 150               # less text than this on the page: no article found
FULL_VERSION = 2             # raise when the extraction improves: kept full articles are redone
MAX_BYTES = 8 * 1024 * 1024
TIMEOUT = 25
WORKERS = 4
OPML_NAME = "feedpond-feeds.opml"
ICONS = True                 # look for the feeds' icons (tests switch it off)
ICON_RETRY = 7 * 86400       # seconds until a feed without an icon is tried again
ICON_BYTES = 512 * 1024
PAGE_BYTES = 3 * 1024 * 1024

# Offline: sites send pictures at full size. Every picture is saved; the big ones are then
# shrunk to the screen's width by the app (Qt can, Python here cannot) - see shrunk()
IMAGE_BYTES = 8 * 1024 * 1024
PICTURES_PER_ARTICLE = 30
SHRINK_BYTES = 24 * 1024     # saved pictures bigger than this become small JPEGs
PICTURE_DAYS = 1             # saved pictures not needed for this long are removed (start, download)

store = None
cache_dir = ""
offline_auto = False         # after each update, save the unread articles for offline reading
icon_problem = ""            # why the last icon download failed (shown on the About page)
_icon_job = threading.Lock()


class Offline(FeedError):
    """The server could not be reached at all."""
events = []                  # filled instead of sending when there is no PyOtherSide
_job = threading.Lock()


def send(name, *args):
    if pyotherside:
        pyotherside.send(name, *args)
    else:
        events.append((name,) + args)


# ---------------------------------------------------------------- network

def normalise_url(text):
    url = (text or "").strip()
    if url.lower().startswith("feed://"):
        url = "http://" + url[7:]
    elif url.lower().startswith("feed:"):
        url = url[5:]
    if "://" not in url:
        url = "https://" + url
    if not url.lower().startswith(feedparse.WEB) or len(url) < 11 or " " in url:
        raise FeedError("Not a web address: %s" % (text or "").strip())
    return url


def fetch(url, etag="", modified="", max_bytes=MAX_BYTES, page=False):
    """(data, final url, etag, last-modified); data is None when nothing changed.
    page = a web page for reading, asked for the way a browser does."""
    headers = {"User-Agent": PAGE_AGENT if page else USER_AGENT,
               "Accept": PAGE_ACCEPT if page else ACCEPT, "Accept-Encoding": "gzip"}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=TIMEOUT) as reply:
            data = reply.read(max_bytes + 1)
            if reply.headers.get("Content-Encoding", "").lower() == "gzip":
                data = zlib.decompressobj(31).decompress(data, max_bytes + 1)
            if len(data) > max_bytes:
                raise FeedError("The file is too large")
            return (data, reply.geturl(), reply.headers.get("ETag", ""),
                    reply.headers.get("Last-Modified", ""))
    except urllib.error.HTTPError as err:
        err.close()
        if err.code == 304:
            return None, url, etag, modified
        raise FeedError("The server answered %d %s" % (err.code, err.reason or ""))
    except urllib.error.URLError as err:
        raise Offline("No connection (%s)" % err.reason)
    except (OSError, ValueError, zlib.error, http.client.HTTPException) as err:
        raise FeedError("Download failed (%s)" % (err or type(err).__name__))


# ---------------------------------------------------------------- feed icons

def _icon_type(data):
    """File extension for image data Qt can show; "" for anything else."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"\x00\x00\x01\x00":
        return "ico"
    return ""


def _picture_type(data):
    """Like _icon_type, for article pictures (WebP as well)."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    kind = _icon_type(data)
    return "" if kind == "ico" else kind


# ---------------------------------------------------------------- offline pictures
# A saved picture is a file named after its address; the article page and the lists
# use it instead of the address when it is there.

def _picture_file(url):
    return os.path.join(cache_dir, "pictures",
                        hashlib.sha1(url.encode("utf-8")).hexdigest())


def local_picture(url):
    """The saved file for a picture address, else the address itself."""
    if not url or not cache_dir:
        return url
    path = _picture_file(url)
    return path if os.path.exists(path) else url


def _save_picture(url):
    """Download one picture (once); False if that failed."""
    path = _picture_file(url)
    if os.path.exists(path):
        try:
            os.utime(path)                    # still needed: the day starts again
        except OSError:
            pass
        return True
    try:
        data = fetch(url, max_bytes=IMAGE_BYTES, page=True)[0]
    except FeedError:
        return False
    kind = _picture_type(data or b"")
    if not kind:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = path + ".part"
    with open(part, "wb") as handle:
        handle.write(data)
    os.replace(part, path)                    # never a half-written picture
    if len(data) > SHRINK_BYTES and kind != "gif":          # GIFs may move: left as they are
        send("shrink", path, kind)
    return True


def shrunk(path, small):
    """The app saved a smaller copy of the picture at `path` as `small`: keep the smaller of
    the two under the picture's name. Returns the bytes saved."""
    folder = os.path.realpath(os.path.join(cache_dir, "pictures"))
    if os.path.dirname(os.path.realpath(path)) != folder or \
            os.path.dirname(os.path.realpath(small)) != folder:
        return 0                               # only pictures of the offline store
    try:
        before, after = os.path.getsize(path), os.path.getsize(small)
    except OSError:
        return 0
    if 0 < after < before:
        os.replace(small, path)
        return before - after
    os.remove(small)
    return 0


def _drop_old_pictures(days=PICTURE_DAYS):
    folder = os.path.join(cache_dir, "pictures")
    limit = time.time() - days * 86400
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        path = os.path.join(folder, name)
        try:
            # Leftovers of an interrupted download or shrinking go as well
            if os.path.getmtime(path) < limit or (
                    "." in name and os.path.getmtime(path) < time.time() - 3600):
                os.remove(path)
        except OSError:
            pass


def _find_icon(feed_id, sites, feed_icon):
    """Download the icon of the first of the web pages `sites` that has one into the cache.
    Returns the file path, "" when there is no usable icon, or None when that could not
    be found out (no connection)."""
    global icon_problem
    offline = False
    tried = set()

    def download(url):
        """The cached file for one icon address, or "" if it is no usable picture."""
        nonlocal offline
        global icon_problem
        if url in tried:
            return ""
        tried.add(url)
        try:
            data = fetch(url, max_bytes=ICON_BYTES)[0]
        except FeedError as err:
            offline = offline or isinstance(err, Offline)
            icon_problem = "%s: %s" % (url, err)
            return ""
        kind = _icon_type(data or b"")
        if not kind:
            icon_problem = "%s: not a PNG, JPEG, GIF or ICO picture" % url
            return ""
        folder = os.path.join(cache_dir, "icons")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "%d.%s" % (feed_id, kind))
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    # Each page in turn: the icons it announces (the best three), then its host's favicon.ico
    for site in sites:
        try:
            page, final, _, _ = fetch(site, max_bytes=PAGE_BYTES)
            candidates = feedparse.icons(page, final)[:3]
        except FeedError as err:
            offline = offline or isinstance(err, Offline)
            icon_problem = "%s: %s" % (site, err)
            candidates, final = [], site
        for url in candidates + [urllib.parse.urljoin(final, "/favicon.ico")]:
            path = download(url)
            if path:
                return path
    if feed_icon:                                 # last: the picture the feed itself names
        path = download(feed_icon)
        if path:
            return path
    return None if offline else ""


def _origin(url):
    parts = urllib.parse.urlsplit(url)
    return "%s://%s/" % (parts.scheme, parts.netloc) if parts.netloc else ""


def _icon_due(feed):
    """True if the feed's icon should be looked for now."""
    if feed.get("icon"):
        return not os.path.exists(feed["icon"])           # the cache was cleared
    return time.time() - feed.get("icon_checked", 0) >= ICON_RETRY


def _want_icon(feed, parsed=None):
    """Look for the feed's icon if it has none and the last try is a week ago.
    Returns True if one was found."""
    global icon_problem
    if not ICONS or not _icon_due(feed):
        return False
    parsed = parsed or {}
    # The website the feed names, that site's front page, then the feed's own host
    site = parsed.get("site") or feed.get("site") or ""
    sites = []
    for page in (site, _origin(site), _origin(feed["url"])):
        if page and page not in sites:
            sites.append(page)
    try:
        path = _find_icon(feed["id"], sites, parsed.get("icon") or "")
    except Exception as err:                      # an icon is never worth a failed update
        icon_problem = "%s: %s" % (type(err).__name__, err)
        path = None
    if path is not None:                          # None: try again at the next chance
        store.set_icon(feed["id"], path)
    return bool(path)


def find_icons(again=False):
    """Quietly fetch the icons of the feeds that have none, in the background.
    again = also the feeds tried within the last week. Returns how many are tried."""
    if again:
        store.forget_icon_checks()
    todo = [f for f in store.feeds() if _icon_due(f)]
    if not ICONS or not todo or not _icon_job.acquire(False):
        return 0

    def work():
        try:
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                found = sum(pool.map(_want_icon, todo))
        finally:
            _icon_job.release()
        send("icons", found)
        if found:
            send("changed", store.unread_total())

    threading.Thread(target=work, daemon=True).start()
    return len(todo)


def icon_status():
    """One paragraph for the About page."""
    feeds = store.feeds()
    have = len([f for f in feeds if _icon_file(f["icon"])])
    text = "%d of %d feeds have an icon." % (have, len(feeds))
    if have < len(feeds) and icon_problem:
        text += " Last problem: " + icon_problem
    return text


def _drop_icon(feed):
    if feed and feed.get("icon"):
        try:
            os.remove(feed["icon"])
        except OSError:
            pass


# ---------------------------------------------------------------- jobs

def _start(work, *args):
    if not _job.acquire(False):
        return False

    def run():
        try:
            send("busy", True, 0, 0)
            work(*args)
        except FeedError as err:
            send("notice", str(err))
        except Exception as err:                 # a bug: say so instead of hanging "busy"
            send("notice", "Error: %s: %s" % (type(err).__name__, err))
        finally:
            _job.release()
            send("busy", False, 0, 0)
            send("changed", store.unread_total())

    threading.Thread(target=run, daemon=True).start()
    return True


def _update_one(feed):
    """New article count, or -1 if the feed failed (the reason is stored with it)."""
    try:
        data, final, etag, modified = fetch(feed["url"], feed["etag"], feed["modified"])
        if data is None:
            store.mark_checked(feed["id"])
            _want_icon(feed)
            return 0
        parsed = feedparse.parse_feed(data, final)
        new = store.save_result(feed["id"], parsed, etag, modified)
        _want_icon(feed, parsed)
        return new
    except FeedError as err:
        store.set_error(feed["id"], str(err))
    except Exception as err:
        store.set_error(feed["id"], "%s: %s" % (type(err).__name__, err))
    return -1


def _refresh(feeds):
    total, done, new, failed = len(feeds), 0, 0, 0
    if not total:
        return ""
    send("busy", True, 0, total)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for count in pool.map(_update_one, feeds):
            done += 1
            if count < 0:
                failed += 1
            else:
                new += count
            send("busy", True, done, total)
            if done % 10 == 0 and done < total:
                send("changed", store.unread_total())
    text = "1 new article" if new == 1 else "%d new articles" % new
    if failed:
        text += ", 1 feed failed" if failed == 1 else ", %d feeds failed" % failed
    send("notice", text)
    return text


def _pictures_of(item, blocks):
    """The picture addresses offline reading needs for an article."""
    urls = [item.get("image") or ""]
    for block in blocks:
        if block["kind"] == "image":
            urls.append(block["src"])
        elif block["kind"] in ("video", "embed"):
            urls.append(block.get("poster") or "")
    seen = []
    for url in urls:
        if url.lower().startswith(feedparse.WEB) and url not in seen:
            seen.append(url)
    return seen[:PICTURES_PER_ARTICLE]


def _offline_one(item):
    """Save one article's full text and pictures; False if its page could not be read."""
    ok = True
    markup = item["full"]
    if not markup and item["link"] and not feedparse.video_link(item["link"]):
        try:
            markup = _read_page(item)
            store.set_full(item["id"], markup)
        except FeedError:
            ok = False                         # the feed's own text is still there
        except Exception:
            ok = False
    blocks = feedparse.article_blocks(markup or item["content"], item["link"])
    for url in _pictures_of(item, blocks):
        _save_picture(url)
    return ok


def _offline(articles):
    """Save the given articles for reading without a connection."""
    total, done, failed = len(articles), 0, 0
    if not total:
        send("notice", "Nothing unread to save")
        return "Nothing unread to save"
    send("busy", True, 0, total, "offline")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for ok in pool.map(_offline_one, articles):
            done += 1
            failed += 0 if ok else 1
            send("busy", True, done, total, "offline")
    _drop_old_pictures()
    text = ("1 article saved for offline reading" if total == 1
            else "%d articles saved for offline reading" % total)
    if failed:
        text += " (%d only with the feed's text)" % failed
    send("notice", text)
    return text


def set_offline(on):
    """Offline reading: after each update, save the unread articles."""
    global offline_auto
    offline_auto = bool(on)


def download_offline():
    """Save all unread articles (full text and pictures) for offline reading, as a job."""
    return _start(lambda: _offline(store.unread_articles()))


def _add_outlines(outlines):
    fresh = []
    for entry in outlines:
        feed_id, created = store.add_feed(entry["url"], entry.get("title", ""),
                                          entry.get("tag", ""))
        if created:
            fresh.append(store.feed(feed_id))
    known = len(outlines) - len(fresh)
    if not outlines:
        raise FeedError("The OPML file lists no feeds")
    send("notice", "%d feeds imported%s" % (
        len(fresh), ", %d were already there" % known if known else ""))
    send("changed", store.unread_total())
    _refresh(fresh)


def _subscribe(text):
    url = normalise_url(text)
    data, final, etag, modified = fetch(url)
    kind, value = feedparse.classify(data, final)
    if kind == "html":
        if not value:
            raise FeedError("No feed found on this page")
        url = value[0]
        data, final, etag, modified = fetch(url)
        kind, value = feedparse.classify(data, final)
        if kind != "feed":
            raise FeedError("No feed found on this page")
    if kind == "opml":
        _add_outlines(value)
        return
    if kind != "feed":
        raise FeedError("This address is not a feed")
    feed_id, created = store.add_feed(url, value["title"])
    new = store.save_result(feed_id, value, etag, modified)
    _want_icon(store.feed(feed_id), value)
    name = value["title"] or url
    if created:
        send("notice", "Added %s (%d articles)" % (name, new))
    else:
        send("notice", "%s is already in the list" % name)


def _import_file(path):
    if path.startswith("file://"):
        path = urllib.request.url2pathname(path[7:])
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_BYTES + 1)
    except OSError as err:
        raise FeedError("Cannot read the file (%s)" % (err.strerror or err))
    if len(data) > MAX_BYTES:
        raise FeedError("The file is too large")
    _add_outlines(feedparse.parse_opml(data))


# ---------------------------------------------------------------- API

def _data_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"),
                                                           ".local", "share")
    return os.path.join(base, "harbour", "feedpond")


def init(path="", cache=""):
    """Open the database; returns the unread count."""
    global store, cache_dir
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    cache_dir = cache or os.path.join(base, "harbour", "feedpond")
    if not path:
        folder = _data_dir()
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "feeds.sqlite")
    store = Store(path)
    if store.version() < 1:
        # 0.2.0-4 looks in more places: feeds left without an icon get another try now
        store.forget_icon_checks()
        store.set_version(1)
    if store.version() < FULL_VERSION:
        # Full articles kept from an older, less careful extraction are read again
        store.forget_full()
        store.set_version(FULL_VERSION)
    store.prune()                             # feeds stored before the limit, or a new limit
    _drop_old_pictures()                      # also when no download has run for a while
    return store.unread_total()


def feeds():
    return [{"fid": f["id"], "title": f["title"] or f["url"], "url": f["url"],
             "site": f["site"], "tag": f["tag"], "unread": f["unread"], "error": f["error"],
             "icon": _icon_file(f["icon"])}
            for f in store.feeds()]


def _icon_file(path, known=None):
    """The icon path if the file is (still) in the cache, else ""."""
    if not path:
        return ""
    if known is None:
        return path if os.path.exists(path) else ""
    if path not in known:
        known[path] = os.path.exists(path)
    return path if known[path] else ""


def _row_image(row):
    """The article's picture; for a YouTube video without one, the video's preview."""
    if row["image"]:
        return row["image"]
    video = feedparse.video_link(row["link"])
    return video["poster"] if video else ""


def items(feed_id=0, unread_only=False, limit=60, before_published=0, before_id=0):
    known = {}
    return [{"iid": i["id"], "title": i["title"], "link": i["link"], "feed": i["feed"],
             "published": i["published"], "summary": i["summary"], "read": i["read"],
             "image": local_picture(_row_image(i)),
             "feedIcon": _icon_file(i["feed_icon"], known)}
            for i in store.items(int(feed_id), bool(unread_only), int(limit),
                                 int(before_published), int(before_id))]


def open_item(item_id, img_width=0):
    """The article for reading (cleaned markup); marks it read."""
    item = store.item(int(item_id))
    if not item:
        return None
    store.set_read(item["id"], True)
    blocks = _blocks(item, item["content"], img_width)
    shown = [b for b in blocks if b["kind"] != "text" or "<img" in b["html"]]
    return {"iid": item["id"], "title": item["title"], "link": item["link"],
            "feed": item["feed"], "author": item["author"], "published": item["published"],
            "feedIcon": _icon_file(item["feed_icon"]), "blocks": blocks,
            "minutes": reading_minutes(blocks),
            "speech": speech_text(item["title"], blocks),
            # The article's picture, when the text does not show one itself
            "lead": local_picture(item["image"]) if not shown else "",
            "hasFull": bool(item["full"]),
            # A YouTube or Vimeo video has no article text to load
            "isVideo": feedparse.video_link(item["link"]) is not None,
            "unread": store.unread_total()}


WORDS_PER_MINUTE = 200
SECONDS_PER_PICTURE = 10


def reading_minutes(blocks):
    """About how long reading the blocks takes: at least one minute."""
    words = sum(len(feedparse.plain(b["html"]).split()) for b in blocks if b["kind"] == "text")
    pictures = len([b for b in blocks if b["kind"] == "image"])
    seconds = 60.0 * words / WORDS_PER_MINUTE + SECONDS_PER_PICTURE * pictures
    return max(1, int(seconds / 60 + 0.5))


_BREAKS = re.compile(r"<br>|</(?:p|h[1-6]|li|div|blockquote|pre|dd|dt)>", re.I)
_LOOSE = re.compile(r"\s+([.,;:!?…])")


def speech_text(title, blocks):
    """What reading aloud says: the title, then the text one paragraph per line (the line
    breaks make the voice pause). Pictures and videos are left out."""
    lines = [feedparse.plain(title or "")]
    for block in blocks:
        if block["kind"] == "text":
            lines += [feedparse.plain(part) for part in _BREAKS.split(block["html"])]
    # Removed tags leave spaces before punctuation ("<b>part</b> .")
    lines = [_LOOSE.sub(r"\1", line) for line in lines if line]
    # A heading or line without a closing mark would run into the next one
    return "\n".join(line if line[-1] in ".!?:;…\"“”" else line + "."
                     for line in lines)


def _blocks(item, markup, img_width):
    """The article's text, pictures and videos for the article page. A video the feed
    encloses, or the video the article is (a YouTube link), comes first unless the text
    shows it already."""
    blocks = feedparse.article_blocks(markup, item["link"], img_width)
    videos = [b for b in blocks if b["kind"] in ("video", "embed")]
    extra = None
    if item.get("video"):
        extra = {"kind": "video", "src": item["video"], "poster": item.get("image") or ""}
        for block in blocks:                  # the picture standing for it shows in it already
            if block["kind"] == "image" and block["src"] == extra["poster"]:
                blocks.remove(block)
                break
    else:
        extra = feedparse.video_link(item["link"])
    if extra and not any(extra.get("src", "-") == b.get("src") or
                         extra.get("url", "-") == b.get("url") for b in videos):
        blocks.insert(0, extra)
    # Pictures saved for offline reading are shown from the phone
    for block in blocks:
        if block["kind"] == "image":
            block["src"] = local_picture(block["src"])
        elif block.get("poster"):
            block["poster"] = local_picture(block["poster"])
    return blocks


def _read_page(item):
    """The article text from the item's web page (markup for clean_html)."""
    data = fetch(item["link"], max_bytes=PAGE_BYTES, page=True)[0]
    found = feedparse.extract_article(data or b"", item["link"], item["title"])
    if found["length"] < FULL_MIN:
        raise FeedError("No article text found on the page")
    return found["markup"]


def open_full(item_id, img_width=0, again=False):
    """The whole article, read from its web page in the background (once; it is kept).
    Answers with the event full(item_id, {"blocks": [...]} or {"error": text}).
    Returns False if the article has no web address."""
    item = store.item(int(item_id))
    if not item or not item["link"]:
        return False

    def work():
        try:
            markup = item["full"]
            if not markup or again:
                markup = _read_page(item)
                store.set_full(item["id"], markup)
            blocks = _blocks(item, markup, img_width)
            result = {"blocks": blocks, "minutes": reading_minutes(blocks),
                      "speech": speech_text(item["title"], blocks)}
        except FeedError as err:
            result = {"error": str(err)}
        except Exception as err:
            result = {"error": "%s: %s" % (type(err).__name__, err)}
        send("full", item["id"], result)

    threading.Thread(target=work, daemon=True).start()
    return True


def set_read(item_id, read=True):
    store.set_read(int(item_id), bool(read))
    return store.unread_total()


def set_read_many(item_ids, read=True):
    """For the articles scrolled past; returns the unread count."""
    store.set_read_many(item_ids, bool(read))
    return store.unread_total()


def mark_all_read(feed_id=0):
    store.mark_all_read(int(feed_id))
    send("changed", store.unread_total())


def remove_feed(feed_id):
    _drop_icon(store.feed(int(feed_id)))
    store.remove_feed(int(feed_id))
    send("changed", store.unread_total())


def subscribe(url):
    """Add a feed by its address, the address of its website, or an OPML address."""
    return _start(_subscribe, url)


def import_opml(path):
    return _start(_import_file, str(path))


def refresh(feed_id=0):
    def work():
        if feed_id:
            feed = store.feed(int(feed_id))
            if feed:
                feed["icon_checked"] = 0         # asked for by hand: look for the icon again
            updated = _refresh([feed] if feed else [])
        else:
            updated = _refresh(store.feeds())
        if offline_auto:
            articles = store.unread_articles()
            if feed_id:
                articles = [a for a in articles if a["feed_id"] == int(feed_id)]
            if articles:
                saved = _offline(articles)
                send("notice", "%s · %s" % (updated, saved) if updated else saved)
    return _start(work)


def export_opml(folder=""):
    """Write all subscriptions to Documents; returns the file path."""
    folder = folder or os.path.join(os.path.expanduser("~"), "Documents")
    path = os.path.join(folder, OPML_NAME)
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(feedparse.build_opml(store.feeds()))
    except OSError as err:
        send("notice", "Export failed (%s)" % (err.strerror or err))
        return ""
    send("notice", "Saved %s" % path)
    return path
