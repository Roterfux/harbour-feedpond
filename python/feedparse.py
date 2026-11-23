# Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
"""Feeds (RSS 0.9x/2.0, RSS 1.0/RDF, Atom), OPML and article HTML.

Pure standard library, no network and no storage: bytes in, plain dicts out.
"""
import calendar
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from html.entities import name2codepoint
from html.parser import HTMLParser
from urllib.parse import urljoin
from xml.sax.saxutils import quoteattr

MAX_ENTRIES = 500
WEB = ("http://", "https://")


class FeedError(Exception):
    """Something the user should read: bad address, not a feed, broken file."""


# ---------------------------------------------------------------- XML

_BOM = b"\xef\xbb\xbf"
_DECL = re.compile(r"^\s*<\?xml[^>]*\?>")
_DECL_ENCODING = re.compile(rb"""^<\?xml[^>]*encoding=["']([\w.-]+)["']""")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_NAMED = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_BARE_AMP = re.compile(r"&(?!(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)")
_XML_NAMES = ("amp", "lt", "gt", "quot", "apos")


def _named(match):
    name = match.group(1)
    if name in _XML_NAMES:
        return match.group(0)
    code = name2codepoint.get(name)
    return "&#%d;" % code if code else "&amp;%s;" % name


def parse_xml(data):
    """Parse XML bytes; repair the usual feed sloppiness on a second try."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if data.startswith(_BOM):
        data = data[len(_BOM):]
    data = data.lstrip()
    if re.search(rb"<!ENTITY", data[:65536], re.I):
        raise FeedError("The file defines its own XML entities, which is not supported")
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        pass
    found = _DECL_ENCODING.match(data)
    encoding = found.group(1).decode("ascii") if found else "utf-8"
    try:
        text = data.decode(encoding, "replace")
    except LookupError:
        text = data.decode("utf-8", "replace")
    text = _DECL.sub("", text, count=1)
    text = _CONTROL.sub("", text)
    text = _NAMED.sub(_named, text)      # &nbsp; and friends are HTML, not XML
    text = _BARE_AMP.sub("&amp;", text)  # "Tom & Jerry"
    try:
        return ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as err:
        raise FeedError("Not valid XML (%s)" % err)


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _media(tag):
    return isinstance(tag, str) and "search.yahoo.com/mrss" in tag


def _first(el, *names):
    """The first child with one of the names; earlier names win."""
    for name in names:
        for child in el:
            if _local(child.tag) == name and not _media(child.tag):
                return child
    return None


def _children(el, name):
    return [c for c in el if _local(c.tag) == name]


def _text(el):
    return "".join(el.itertext()).strip() if el is not None else ""


# ---------------------------------------------------------------- text

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_HIDDEN = re.compile(r"<(script|style)\b.*?</\1\s*>", re.I | re.S)


def plain(text):
    """One line of plain text from text that may carry markup."""
    text = _TAG.sub(" ", _HIDDEN.sub(" ", text or ""))
    return _SPACE.sub(" ", html.unescape(text)).strip()


def summary(markup, limit=220):
    text = plain(markup)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


_ISO = re.compile(r"(\d{4})-(\d\d)-(\d\d)"
                  r"(?:[T ](\d\d):(\d\d)(?::(\d\d))?(?:[.,]\d+)?\s*(Z|[+-]\d\d:?\d\d)?)?", re.I)


def parse_date(text):
    """Unix time (UTC seconds) of an RFC 822 or ISO 8601 date; 0 if unreadable."""
    text = (text or "").strip()
    if not text:
        return 0
    m = _ISO.match(text)
    if m:
        parts = [int(g or 0) for g in m.groups()[:6]]
        try:
            stamp = calendar.timegm(tuple(parts) + (0, 0, 0))
        except (ValueError, OverflowError):
            return 0
        zone = m.group(7)
        if zone and zone.upper() != "Z":
            digits = zone[1:].replace(":", "")
            shift = int(digits[:2]) * 3600 + int(digits[2:]) * 60
            stamp -= shift if zone[0] == "+" else -shift
        return max(0, stamp)
    try:
        when = parsedate_to_datetime(text)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0, int(when.timestamp()))
    except (TypeError, ValueError, IndexError, OverflowError):
        return 0


# ---------------------------------------------------------------- feeds

def _web(url):
    return url if url.lower().startswith(WEB) else ""


def _link(el, base):
    fallback = ""
    for child in el:
        if _local(child.tag) != "link" or _media(child.tag):
            continue
        href = child.get("href")
        if href is not None:                      # Atom style
            if (child.get("rel") or "alternate").lower() == "alternate":
                return _web(urljoin(base, href.strip()))
        elif (child.text or "").strip() and not fallback:
            fallback = child.text.strip()         # RSS style
    return _web(urljoin(base, fallback)) if fallback else ""


def _body(el, atom):
    if el is None:
        return ""
    kind = (el.get("type") or "").lower()
    if len(el) or kind == "xhtml":                # markup as real child elements
        return (el.text or "") + "".join(
            ET.tostring(child, encoding="unicode", method="html") for child in el)
    text = el.text or ""
    if atom and kind in ("", "text"):
        return html.escape(text)
    return text


def _author(el):
    node = _first(el, "creator", "author")
    if node is None:
        return ""
    name = _first(node, "name")
    return plain(_text(name if name is not None else node))


def _entry(el, base, atom):
    title = plain(_text(_first(el, "title")))
    link = _link(el, base)
    guid = _text(_first(el, "guid", "id"))
    if not link and guid.lower().startswith(WEB):
        link = guid
    content = _body(_first(el, "encoded", "content", "description", "summary"), atom)
    date = _text(_first(el, "pubdate", "published", "date", "updated", "modified"))
    if not title:
        title = summary(content, 80)
    if not guid:
        guid = link or hashlib.sha1((title + "\n" + date).encode("utf-8")).hexdigest()
    return {"guid": guid, "title": title, "link": link, "author": _author(el),
            "published": parse_date(date), "content": content.strip(),
            "summary": summary(content), "image": _entry_image(el, link or base, content),
            "video": _entry_video(el, link or base)}


_IMAGE_NAME = re.compile(r"\.(jpe?g|png|gif|webp)(\?|$)", re.I)
_VIDEO_NAME = re.compile(r"\.(mp4|m4v|webm|mov|m3u8)(\?|$)", re.I)


def _entry_video(el, base):
    """A video file the article comes with (enclosure or Media RSS), else ""."""
    for node in el.iter():
        name = _local(node.tag)
        kind = (node.get("type") or "").lower()
        if (_media(node.tag) and name == "content") or name == "enclosure":
            url = node.get("url") or ""
        elif name == "link" and (node.get("rel") or "").lower() == "enclosure":
            url = node.get("href") or ""
        else:
            continue
        if kind.startswith("video/") or (node.get("medium") or "").lower() == "video" \
                or (not kind and _VIDEO_NAME.search(url)):
            url = _web(urljoin(base, url.strip()))
            if url:
                return url
    return ""


def _entry_image(el, base, content):
    """The picture that stands for an article: Media RSS thumbnail or content, an image
    enclosure, or else the first real picture in its text. Of several sizes, the smallest
    one PICTURE_WIDTH wide (else the widest), to keep downloads small."""
    found = []                                   # (width, address)
    for node in el.iter():
        name = _local(node.tag)
        kind = (node.get("type") or "").lower()
        if _media(node.tag) and name == "thumbnail":
            url = node.get("url")
        elif (_media(node.tag) and name == "content") or name == "enclosure":
            url = node.get("url") or ""
            if not (kind.startswith("image/") or (node.get("medium") or "").lower() == "image"
                    or (not kind and _IMAGE_NAME.search(url))):
                continue
        elif name == "link" and (node.get("rel") or "").lower() == "enclosure" \
                and kind.startswith("image/"):
            url = node.get("href")
        else:
            continue
        url = _web(urljoin(base, (url or "").strip()))
        if url:
            found.append((_number(node.get("width")), url))
    if not found:
        return first_image(content, base)
    wide_enough = sorted(f for f in found if f[0] >= PICTURE_WIDTH)
    if wide_enough:
        return wide_enough[0][1]
    widest = max(f[0] for f in found)
    return [url for width, url in found if width == widest][0]   # the first of the widest


def _feed_icon(head, base):
    """The feed's own picture: Atom <icon>/<logo> or RSS <image><url>."""
    node = _first(head, "icon", "logo")
    if node is None:
        image = _first(head, "image")
        node = _first(image, "url") if image is not None else None
    url = _text(node)
    return _web(urljoin(base, url)) if url else ""


def _feed(root, base):
    kind = _local(root.tag)
    if kind == "rss":
        head = _first(root, "channel")
        if head is None:
            raise FeedError("The feed has no channel")
        entries = _children(head, "item")
    elif kind == "rdf":
        head = _first(root, "channel")
        if head is None:
            head = root
        entries = _children(root, "item") or _children(head, "item")
    elif kind == "feed":
        head = root
        entries = _children(root, "entry")
    else:
        raise FeedError("This is not a feed")
    atom = kind == "feed"
    seen = set()
    items = []
    for el in entries[:MAX_ENTRIES]:
        item = _entry(el, base, atom)
        if item["guid"] not in seen and (item["title"] or item["link"]):
            seen.add(item["guid"])
            items.append(item)
    return {"title": plain(_text(_first(head, "title"))), "site": _link(head, base),
            "icon": _feed_icon(head, base), "items": items}


def parse_feed(data, base_url=""):
    """{"title", "site", "icon", "items": [{"guid", "title", "link", "author", "published",
    "content", "summary", "image"}]} - items in the feed's own order (normally newest first)."""
    return _feed(parse_xml(data), base_url)


# ---------------------------------------------------------------- OPML

def _outlines(root):
    found = []
    seen = set()

    def walk(el, folder):
        for child in el:
            if _local(child.tag) != "outline":
                continue
            attrs = {key.lower(): value for key, value in child.attrib.items()}
            name = plain(attrs.get("text") or attrs.get("title") or "")
            url = (attrs.get("xmlurl") or "").strip()
            if url.lower().startswith("feed://"):
                url = "http://" + url[7:]
            if _web(url):
                if url not in seen:
                    seen.add(url)
                    found.append({"url": url, "title": name, "tag": folder})
                walk(child, folder)
            else:
                walk(child, name or folder)

    body = _first(root, "body")
    walk(body if body is not None else root, "")
    return found


def parse_opml(data):
    """[{"url", "title", "tag"}] - tag is the name of the folder the feed is in."""
    root = parse_xml(data)
    if _local(root.tag) != "opml":
        raise FeedError("This is not an OPML file")
    return _outlines(root)


def build_opml(feeds, title="Feedpond subscriptions"):
    """OPML 2.0 bytes for [{"url", "title", "site", "tag"}]."""
    def line(feed, indent):
        site = " htmlUrl=%s" % quoteattr(feed["site"]) if feed.get("site") else ""
        name = quoteattr(feed.get("title") or feed["url"])
        return '%s<outline type="rss" text=%s title=%s xmlUrl=%s%s/>' % (
            indent, name, name, quoteattr(feed["url"]), site)

    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<opml version="2.0">',
           "  <head><title>%s</title></head>" % html.escape(title), "  <body>"]
    folders = {}
    for feed in feeds:
        folders.setdefault(feed.get("tag") or "", []).append(feed)
    for feed in folders.pop("", []):
        out.append(line(feed, "    "))
    for folder in sorted(folders, key=str.lower):
        out.append("    <outline text=%s title=%s>" % (quoteattr(folder), quoteattr(folder)))
        out.extend(line(feed, "      ") for feed in folders[folder])
        out.append("    </outline>")
    out += ["  </body>", "</opml>", ""]
    return "\n".join(out).encode("utf-8")


# ---------------------------------------------------------------- HTML pages

_FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/rdf+xml",
               "application/xml", "text/xml")


class _LinkFinder(HTMLParser):
    def __init__(self, base):
        HTMLParser.__init__(self)
        self.base = base
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = {key: (value or "") for key, value in attrs}
        if "alternate" not in a.get("rel", "").lower().split():
            return
        if a.get("type", "").lower().strip() not in _FEED_TYPES[:3] or not a.get("href"):
            return
        url = _web(urljoin(self.base, a["href"].strip()))
        if url and url not in self.links:
            self.links.append(url)


class _IconFinder(HTMLParser):
    def __init__(self, base):
        HTMLParser.__init__(self)
        self.base = base
        self.found = []                 # (preference, address)

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = {key: (value or "") for key, value in attrs}
        rel = a.get("rel", "").lower().split()
        touch = any(word.startswith("apple-touch-icon") for word in rel)
        if not touch and "icon" not in rel:
            return
        url = _web(urljoin(self.base, a.get("href", "").strip()))
        if not url or "svg" in a.get("type", "").lower() or url.lower().endswith(".svg"):
            return
        size = _number(a.get("sizes")) or (180 if touch else 16)
        # Best: the smallest one that is still sharp in a list; else the largest
        self.found.append(((0, size) if size >= 64 else (1, -size), url))


def icons(data, base_url=""):
    """The icon addresses a web page announces, the best fitting first."""
    finder = _IconFinder(base_url)
    try:
        finder.feed(data.decode("utf-8", "replace") if isinstance(data, bytes) else data)
        finder.close()
    except Exception:
        pass
    ordered = []
    for _, url in sorted(finder.found):
        if url not in ordered:
            ordered.append(url)
    return ordered


def discover(data, base_url=""):
    """The feed addresses a web page announces in its <link rel="alternate"> tags."""
    finder = _LinkFinder(base_url)
    try:
        finder.feed(data.decode("utf-8", "replace") if isinstance(data, bytes) else data)
        finder.close()
    except Exception:           # a half-parsed page still gives the links found so far
        pass
    return finder.links


def classify(data, base_url=""):
    """What a downloaded document is:
    ("feed", parsed feed), ("opml", outlines), ("html", feed addresses) or ("unknown", None)."""
    head = data[:4096]
    if head.startswith(_BOM):
        head = head[len(_BOM):]
    head = head.lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return "html", discover(data, base_url)
    try:
        root = parse_xml(data)
    except FeedError:
        if b"<html" in head or b"<head" in head:
            return "html", discover(data, base_url)
        return "unknown", None
    kind = _local(root.tag)
    if kind in ("rss", "rdf", "feed"):
        return "feed", _feed(root, base_url)
    if kind == "opml":
        return "opml", _outlines(root)
    if kind == "html":
        return "html", discover(data, base_url)
    return "unknown", None


# ---------------------------------------------------------------- article HTML

# What Qt's rich text shows well; everything else is dropped but its text kept.
_KEEP = frozenset("p br b strong i em u s sub sup ul ol li blockquote pre code tt "
                  "h1 h2 h3 h4 h5 h6 a img hr small big div dl dt dd cite".split())
_AS_DIV = frozenset("section article figure figcaption header footer main aside tr "
                    "table caption details summary address".split())
_SKIP = frozenset("script style iframe noscript svg form head template object embed "
                  "video audio canvas button select textarea math".split())
_VOID = frozenset(("br", "hr", "img"))


def _number(value):
    found = re.match(r"\s*(\d+)", value or "")
    return int(found.group(1)) if found else 0


_EMOJI = re.compile(r"emoji|smiley", re.I)


PICTURE_WIDTH = 480          # of several sizes of a picture, the smallest this wide is used


def _from_srcset(srcset, wanted=PICTURE_WIDTH):
    """From "a.jpg 320w, b.jpg 800w": the smallest picture at least `wanted` pixels wide,
    else the widest; "" if there is none."""
    sizes = []
    for part in srcset.split(","):
        words = part.split()
        if not words or words[0].lower().startswith("data:"):
            continue
        width = _number(words[1]) if len(words) > 1 and words[1].endswith("w") else 0
        sizes.append((width, words[0]))
    if not sizes:
        return ""
    big = sorted(s for s in sizes if s[0] >= wanted)
    return (big[0] if big else max(sizes))[1]


def _picture(a, base, smallest=3):
    """The usable address of an <img> with the attributes a; "" for tracking pixels,
    emoji, inline data and anything declared smaller than `smallest` pixels."""
    # Lazy-loading pages keep the real address aside and a placeholder in src
    src = (a.get("data-src") or a.get("data-lazy-src") or a.get("data-original")
           or a.get("src") or "").strip()
    if not src or src.lower().startswith("data:"):
        src = _from_srcset(a.get("data-srcset") or a.get("srcset") or "")
    url = _web(urljoin(base, src)) if src else ""
    small = any(a.get(side) and _number(a.get(side)) < smallest for side in ("width", "height"))
    if not url or small or _EMOJI.search(a.get("class", "")):
        return ""
    return url


class _FirstImage(HTMLParser):
    def __init__(self, base):
        HTMLParser.__init__(self)
        self.base = base
        self.url = ""

    def handle_starttag(self, tag, attrs):
        if tag == "img" and not self.url:
            self.url = _picture({key: (value or "") for key, value in attrs}, self.base, 50)


def first_image(markup, base_url=""):
    """The first real picture in article markup ("" if there is none)."""
    if "<img" not in (markup or "").lower():
        return ""
    finder = _FirstImage(base_url)
    try:
        finder.feed(markup)
        finder.close()
    except Exception:
        pass
    return finder.url


_YOUTUBE = re.compile(r"(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?(?:.*&)?v=|v/|shorts/|"
                      r"live/)|youtu\.be/)([\w-]{11})", re.I)
_VIMEO = re.compile(r"(?:player\.)?vimeo\.com/(?:video/)?(\d{5,})", re.I)
_SMALL_PICTURE = 100        # pictures declared narrower than this stay in the text


def video_link(url):
    """A video block for the address of a YouTube or Vimeo video (page or player), else None:
    url = the video's page (for the browser and sharing), play = the page that plays it in
    the app's web view (YouTube's mobile page, Vimeo's player)."""
    found = _YOUTUBE.search(url or "")
    if found:
        return {"kind": "embed", "site": "YouTube",
                "url": "https://www.youtube.com/watch?v=" + found.group(1),
                "play": "https://m.youtube.com/watch?v=" + found.group(1),
                "poster": "https://i.ytimg.com/vi/%s/hqdefault.jpg" % found.group(1)}
    found = _VIMEO.search(url or "")
    if found:
        return {"kind": "embed", "site": "Vimeo", "url": "https://vimeo.com/" + found.group(1),
                "play": "https://player.vimeo.com/video/%s?autoplay=1" % found.group(1),
                "poster": ""}
    return None


class _Cleaner(HTMLParser):
    """With blocks=True the article is cut into a list of blocks:
        {"kind": "text", "html": markup for a rich-text Label}
        {"kind": "image", "src", "width", "height", "link"}   (link: around the picture)
        {"kind": "video", "src", "poster"}                     (a file the app can play)
        {"kind": "embed", "url", "poster", "site"}             (YouTube, Vimeo)
    Tags open at a cut are closed before it and opened again after it."""

    def __init__(self, base, img_width, blocks=False):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.base = base
        self.img_width = img_width
        self.blocks = [] if blocks else None
        self.out = []
        self.open = []              # (tag, start markup) of the kept elements now open
        self.skipping = 0
        self.video = None           # the <video> being read

    @staticmethod
    def _name(tag):
        tag = tag.rsplit(":", 1)[-1]
        return "div" if tag in _AS_DIV else tag

    def _address(self, value):
        value = (value or "").strip()
        return _web(urljoin(self.base, value)) if value else ""

    def _link(self):
        for tag, start in reversed(self.open):
            if tag == "a":
                found = re.search(r'href="([^"]*)"', start)
                return html.unescape(found.group(1)) if found else ""
        return ""

    def handle_starttag(self, tag, attrs):
        tag = self._name(tag)
        a = {key: (value or "") for key, value in attrs}
        if not self.skipping:
            if tag == "video":
                self.video = {"kind": "video", "src": self._address(a.get("src")),
                              "poster": self._address(a.get("poster"))}
            elif tag == "iframe":
                embed = video_link(a.get("src") or a.get("data-src"))
                if embed:
                    self._block(embed)
        elif tag == "source" and self.video is not None and not self.video["src"]:
            kind = a.get("type", "").lower()
            if not kind or kind.startswith("video/") or "mpegurl" in kind:
                self.video["src"] = self._address(a.get("src"))
        if tag in _SKIP:
            self.skipping += 1
            return
        if self.skipping or tag not in _KEEP:
            if tag == "td" or tag == "th":
                self.out.append(" ")
            return
        if tag == "img":
            self._image(a)
            return
        if tag == "a":
            url = urljoin(self.base, a.get("href", "").strip())
            if url.lower().startswith(WEB + ("mailto:",)):
                start = '<a href="%s">' % html.escape(url)
            else:
                start = "<a>"
        else:
            start = "<%s>" % tag
        self.out.append(start)
        if tag not in _VOID:
            self.open.append((tag, start))

    def _image(self, a):
        url = _picture(a, self.base)
        width, height = _number(a.get("width")), _number(a.get("height"))
        if not url:                                          # tracking pixels, emoji images
            if _EMOJI.search(a.get("class", "")) and a.get("alt"):
                self.out.append(html.escape(a["alt"], quote=False))
            return
        if self.blocks is not None and not (width and width < _SMALL_PICTURE):
            self._block({"kind": "image", "src": url, "width": width, "height": height,
                         "link": self._link()})
            return
        size = ""
        if self.img_width:
            if width and width < self.img_width:
                size = ' width="%d"' % width
                if height:
                    size += ' height="%d"' % height
            else:
                size = ' width="%d"' % self.img_width        # Qt keeps the aspect ratio
        if self.blocks is not None:                          # a small one, inside the text
            self.out.append('<img src="%s"%s>' % (html.escape(url), size))
        else:
            self.out.append('<br><img src="%s"%s><br>' % (html.escape(url), size))

    def _flush(self, ending=""):
        text = ("".join(self.out) + ending).strip()
        if text and (plain(text) or "<img" in text):
            self.blocks.append({"kind": "text", "html": text})

    def _block(self, block):
        if self.blocks is None:                              # one markup string: a link
            if block.get("kind") != "image":
                url = block.get("url") or block.get("src")
                self.out.append('<br><a href="%s">%s</a><br>' % (
                    html.escape(url), html.escape(block.get("site") or "Video")))
            return
        self._flush("".join("</%s>" % tag for tag, _ in reversed(self.open)))
        self.blocks.append(block)
        self.out = [start for _, start in self.open]

    def handle_endtag(self, tag):
        tag = self._name(tag)
        if tag == "video" and self.video is not None:
            video, self.video = self.video, None
            self.skipping = max(0, self.skipping - 1)
            if video["src"]:
                self._block(video)
            return
        if tag in _SKIP:
            self.skipping = max(0, self.skipping - 1)
            return
        if self.skipping or tag not in _KEEP or tag in _VOID:
            return
        for depth in range(len(self.open) - 1, -1, -1):      # stray end tags are dropped
            if self.open[depth][0] == tag:
                for inner, _ in reversed(self.open[depth:]):
                    self.out.append("</%s>" % inner)
                del self.open[depth:]
                return

    def handle_data(self, data):
        if not self.skipping:
            self.out.append(html.escape(data, quote=False))


def clean_html(markup, base_url="", img_width=0):
    """Article markup reduced to what a QML rich-text Label shows safely: no scripts,
    styles or frames, absolute links, images scaled to img_width pixels."""
    cleaner = _Cleaner(base_url, int(img_width or 0))
    try:
        cleaner.feed(markup or "")
        cleaner.close()
    except Exception:
        return html.escape(plain(markup))
    return "".join(cleaner.out).strip()


def article_blocks(markup, base_url="", img_width=0):
    """The article cut into text, picture and video blocks (see _Cleaner)."""
    cleaner = _Cleaner(base_url, int(img_width or 0), blocks=True)
    try:
        cleaner.feed(markup or "")
        cleaner.close()
    except Exception:
        text = html.escape(plain(markup))
        return [{"kind": "text", "html": text}] if text else []
    cleaner._flush("".join("</%s>" % tag for tag, _ in reversed(cleaner.open)))
    return cleaner.blocks


# ---------------------------------------------------------------- full articles
# The article text of a web page, found the way "reader views" do: the element whose
# paragraphs hold the most prose wins; menus, comments, sharing bars and the like are dropped.

_VOID_ALL = frozenset("area base br col embed hr img input link meta param source track "
                      "wbr".split())
_BLOCKS = frozenset("address article aside blockquote dd details div dl dt figure footer form "
                    "h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section table ul".split())
_JUNK = frozenset("script style noscript svg form button select textarea input nav "
                  "aside footer template object embed canvas math head dialog".split())
_NO_TEXT = _JUNK | frozenset(("iframe", "video", "audio"))    # their text is not article text
_NEGATIVE = re.compile(r"comment|sidebar|sponsor|advert|\bads?\b|promo|related|recommend|"
                       r"share|sharing|social|newsletter|subscri|signup|cookie|consent|popup|"
                       r"modal|menu|breadcrumb|banner|masthead|widget|outbrain|taboola|"
                       r"paginat|pager|disqus|footer|header|teaser|toolbar|login|\bnav|"
                       r"autorbox|author-?(?:box|bio|info|card)|about-the-author", re.I)
_POSITIVE = re.compile(r"article|body|content|entry|main|post|text|story|prose|blog", re.I)
_BUTTON = re.compile(r"button|\bbtn\b|\bcta\b", re.I)
# A "see also" label whose link list was left out, at the very end of the article
_TRAILER = re.compile(r"<(b|strong|em|i|span|p|h[1-6])>\s*(?:siehe auch|mehr zum thema|lesen sie "
                      r"auch|auch interessant|weitere artikel|weiterlesen|see also|related|"
                      r"read more|more on this)\b[^<]{0,40}</\1>(?=(?:\s|<br>|</[a-z0-9]+>)*$)",
                      re.I)
_ROLES = frozenset("navigation complementary dialog banner contentinfo menu menubar "
                   "alert search".split())
_TAG_SCORE = {"div": 5, "article": 10, "main": 5, "section": 2, "pre": 3, "td": 3,
              "blockquote": 3, "form": -3, "ol": -3, "ul": -3, "dl": -3, "dd": -3, "dt": -3,
              "li": -3, "address": -3, "th": -5, "h1": -5, "h2": -5, "h3": -5, "h4": -5,
              "h5": -5, "h6": -5}
_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([\w.:-]+)""", re.I)
_MAX_DEPTH = 250


class _Node:
    __slots__ = ("tag", "attrs", "kids", "parent", "score", "text")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.kids = []
        self.score = 0.0
        self.text = None


class _Tree(HTMLParser):
    """A forgiving element tree: stray end tags are ignored, unclosed ones end with
    their parent, and a new block ends an open <p>."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.root = _Node("#root", {}, None)
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _BLOCKS and self.stack[-1].tag == "p":
            self.stack.pop()
        if len(self.stack) >= _MAX_DEPTH and tag not in _VOID_ALL:
            return                            # too deep: only the text is kept
        node = _Node(tag, {k.lower(): (v or "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].kids.append(node)
        if tag not in _VOID_ALL:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.lower() and len(self.stack) > 1:
            self.stack.pop()

    def handle_endtag(self, tag):
        tag = tag.lower()
        for depth in range(len(self.stack) - 1, 0, -1):
            if self.stack[depth].tag == tag:
                del self.stack[depth:]
                return

    def handle_data(self, data):
        self.stack[-1].kids.append(data)


def _elements(node):
    return [kid for kid in node.kids if isinstance(kid, _Node)]


def _walk(node):
    """All elements below node, depth first."""
    todo = list(reversed(_elements(node)))
    while todo:
        kid = todo.pop()
        yield kid
        todo.extend(reversed(_elements(kid)))


def _inner(node):
    """The element's visible text, spaces collapsed."""
    if node.text is None:
        parts = [kid if isinstance(kid, str) else _inner(kid)
                 for kid in node.kids if isinstance(kid, str) or kid.tag not in _NO_TEXT]
        node.text = _SPACE.sub(" ", " ".join(parts)).strip()
    return node.text


def _link_share(node):
    """How much of the element's text is link text (0..1)."""
    length = len(_inner(node))
    if not length:
        return 1.0
    linked = sum(len(_inner(a)) for a in _walk(node) if a.tag == "a")
    return min(1.0, linked / length)


def _names(node):
    return node.attrs.get("class", "") + " " + node.attrs.get("id", "")


def _unlikely(node, by_name=True):
    a = node.attrs
    if node.tag == "iframe":                  # only video players are kept
        return not video_link(a.get("src") or a.get("data-src"))
    if node.tag in _JUNK or "hidden" in a or a.get("aria-hidden") == "true":
        return True
    if re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", a.get("style", ""), re.I):
        return True
    # Shop buttons ("Zum Angebot") and other paid links dressed as buttons
    if node.tag == "a" and (_BUTTON.search(a.get("class", "")) or (
            "sponsored" in a.get("rel", "").lower() and any(
                k.tag in _BLOCKS or k.tag == "span" for k in _elements(node)))):
        return True
    if not by_name or node.tag in ("html", "body", "article", "main", "a", "p"):
        return False
    if a.get("role", "").lower() in _ROLES:
        return True
    names = _names(node)
    return bool(_NEGATIVE.search(names)) and not _POSITIVE.search(names)


def _prune(root, by_name=True):
    todo = [root]
    while todo:
        node = todo.pop()
        node.kids = [k for k in node.kids if isinstance(k, str) or not _unlikely(k, by_name)]
        todo.extend(_elements(node))


def _weight(node):
    names = _names(node)
    return (25 if _POSITIVE.search(names) else 0) - (25 if _NEGATIVE.search(names) else 0)


def _is_paragraph(node):
    if node.tag in ("p", "pre", "td"):
        return True
    # A <div> holding only text and inline markup is a paragraph as well
    return node.tag == "div" and not any(k.tag in _BLOCKS for k in _walk(node))


def _runs(node):
    """The stretches of text an element holds itself, outside block children and split at
    <br> (pages that write their article without <p>)."""
    runs, current = [], []
    for kid in node.kids:
        if isinstance(kid, str):
            current.append(kid)
        elif kid.tag in _BLOCKS or kid.tag == "br" or kid.tag in _NO_TEXT:
            runs.append(" ".join(current))
            current = []
        else:
            current.append(_inner(kid))
    runs.append(" ".join(current))
    return [run for run in (_SPACE.sub(" ", r).strip() for r in runs) if len(run) >= 25]


def _best(root):
    """The element holding the article, and all scored elements."""
    scored = {}
    texts = []                                # (text, the element it counts for first)
    for node in _walk(root):
        if _is_paragraph(node):
            texts.append((_inner(node), node.parent))
        else:
            texts.extend((run, node) for run in _runs(node))
    for text, first in texts:
        if len(text) < 25:
            continue
        points = 1 + text.count(",") + text.count("，") + min(len(text) // 100, 3)
        node, level = first, 0
        while node is not None and node is not root and level < 3:
            if id(node) not in scored:
                node.score = _TAG_SCORE.get(node.tag, 0) + _weight(node)
                scored[id(node)] = node
            node.score += points / (1, 2, 6)[level]
            node, level = node.parent, level + 1
    best = None
    for node in scored.values():
        node.score *= 1 - _link_share(node)
        if best is None or node.score > best.score:
            best = node
    return best, scored


def _with_siblings(best, scored):
    """The best element and those beside it that belong to the article, too
    (pages that split the text over several blocks)."""
    parent = best.parent
    if parent is None or parent.tag == "#root":
        return [best]
    least = max(10.0, best.score * 0.2)
    keep = []
    for kid in _elements(parent):
        if kid is best:
            keep.append(kid)
        elif id(kid) in scored and kid.score >= least:
            keep.append(kid)
        elif kid.tag == "p":
            text = _inner(kid)
            share = _link_share(kid)
            if (len(text) > 80 and share < 0.25) or (
                    0 < len(text) <= 80 and share == 0 and re.search(r"\.( |$)", text)):
                keep.append(kid)
    return keep


def _attrs(node, base):
    """The attributes the cleaner uses, with absolute addresses."""
    a = node.attrs
    if node.tag == "a":
        href = a.get("href", "").strip()
        return ' href="%s"' % html.escape(urljoin(base, href)) if href else ""
    if node.tag == "img":
        src = _picture(a, base)
        if not src:
            src = a.get("src", "")
        out = ' src="%s"' % html.escape(src)
        for key in ("width", "height", "alt", "class"):
            if a.get(key):
                out += ' %s="%s"' % (key, html.escape(a[key]))
        return out
    if node.tag in ("video", "source", "iframe"):
        out = ""
        for key in ("src", "data-src", "poster"):
            if a.get(key, "").strip():
                out += ' %s="%s"' % (key, html.escape(urljoin(base, a[key].strip())))
        if a.get("type"):
            out += ' type="%s"' % html.escape(a["type"])
        return out
    return ""


_LISTISH = frozenset("ul ol dl div section table aside nav".split())


def _markup(nodes, base, title, out, small=0, top=True):
    """Write the elements as HTML; small > 0: leave out blocks that look like sharing bars,
    related links etc. by their class names and hold less text than that. Inside the
    article, lists and blocks that are mostly links ("read also") are left out."""
    for node in nodes:
        if isinstance(node, str):
            out.append(html.escape(node, quote=False))
            continue
        if node.tag in _JUNK:
            continue
        if node.tag in ("h1", "h2") and title and _inner(node).lower() == title:
            continue                          # the title is shown above the text already
        if small and _unlikely(node) and len(_inner(node)) < small:
            continue
        if not top and node.tag in _LISTISH and _inner(node) and _link_share(node) > 0.5 \
                and not any(n.tag in ("img", "video", "iframe") for n in _walk(node)):
            continue
        out.append("<%s%s>" % (node.tag, _attrs(node, base)))
        if node.tag not in _VOID_ALL:
            _markup(node.kids, base, title, out, small, False)
            out.append("</%s>" % node.tag)


def _decode(data):
    if isinstance(data, str):
        return data
    if data.startswith(_BOM):
        return data[len(_BOM):].decode("utf-8", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    found = _CHARSET.search(data[:4096])
    if found:
        try:
            return data.decode(found.group(1).decode("ascii"), "replace")
        except (LookupError, UnicodeDecodeError):
            pass
    return data.decode("cp1252", "replace")


def _parse_page(text):
    tree = _Tree()
    try:
        tree.feed(text)
        tree.close()
    except Exception:
        pass                                  # what was read so far is still used
    return tree.root


def _article(root, base_url, title, by_name):
    """(markup, text length) of the article in the page tree."""
    _prune(root, by_name)
    marked = [n for n in _walk(root) if "articlebody" in n.attrs.get("itemprop", "").lower()]
    if marked and len(_inner(marked[0])) >= 250:
        nodes = marked[:1]
    else:
        best, scored = _best(root)
        if not best:
            return "", 0
        nodes = _with_siblings(best, scored)
    length = sum(len(_inner(n)) for n in nodes)
    out = []
    _markup(nodes, base_url, title, out, 0 if by_name else length * 0.3)
    return _TRAILER.sub("", "".join(out).rstrip()), length


def _structured_body(script):
    """The longest articleBody in one <script type="application/ld+json"> (schema.org data
    for search engines), "" if there is none."""
    try:
        data = json.loads(script)
    except ValueError:
        return ""
    best, todo = "", [data]
    while todo:
        value = todo.pop()
        if isinstance(value, dict):
            body = value.get("articleBody")
            if isinstance(body, str) and len(body) > len(best):
                best = body
            todo.extend(value.values())
        elif isinstance(value, list):
            todo.extend(value)
    return best


def _text_markup(text, size=400):
    """Plain article text as paragraphs: its own line breaks, else sentences put together
    into paragraphs of about `size` characters."""
    text = html.unescape(text).replace("\r", "")
    if "<" in text and ">" in text:
        text = plain(text)
    if "\n" in text.strip():
        parts = [p.strip() for p in re.split(r"\n\s*\n|\n", text)]
    else:
        parts, current = [], ""
        for sentence in re.split(r"(?<=[.!?:“\"])\s+(?=[\"„“(A-ZÄÖÜ0-9])",
                                 text.strip()):
            current = (current + " " + sentence).strip()
            if len(current) >= size:
                parts.append(current)
                current = ""
        parts.append(current)
    return "".join("<p>%s</p>" % html.escape(p, quote=False) for p in parts if p)


def extract_article(data, base_url="", title=""):
    """The article in a web page: {"markup": its HTML (for clean_html), "length": how much
    text it has}. The page's main picture leads the text when the text has none."""
    text = _decode(data)
    root = _parse_page(text)
    lead, page_title, structured = "", "", ""
    for node in _walk(root):
        a = node.attrs
        if node.tag == "script" and "ld+json" in a.get("type", "").lower():
            body = _structured_body("".join(k for k in node.kids if isinstance(k, str)))
            if len(body) > len(structured):
                structured = body
        elif node.tag == "meta" and not lead:
            if (a.get("property") or a.get("name") or "").lower() in ("og:image",
                                                                       "twitter:image"):
                lead = _web(urljoin(base_url, a.get("content", "").strip()))
        elif node.tag == "title" and not page_title:
            page_title = _inner(node)
    wanted = _SPACE.sub(" ", title or "").strip().lower()
    try:
        markup, length = _article(root, base_url, wanted, True)
        if length < 500:
            # Pages that wrap everything in a "...WithSidebar..." block lose the article
            # to the class names: once more without judging them
            again = _article(_parse_page(text), base_url, wanted, False)
            if again[1] > 2 * length + 100:
                markup, length = again
    except RecursionError:
        raise FeedError("The page is too deeply nested to read")
    # Pages that show their text only after a consent or ad check (winfuture.de) still
    # carry all of it in their data for search engines
    body = _SPACE.sub(" ", structured).strip()
    if len(body) >= 300 and len(body) > 1.5 * length:
        markup, length = _text_markup(structured), len(body)
    if lead and not first_image(markup, base_url):
        markup = '<img src="%s">' % html.escape(lead) + markup
    return {"markup": markup, "length": length, "title": page_title}
