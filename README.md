# Feedpond

A feed reader for Sailfish OS without an account: RSS and Atom feeds are downloaded straight
from their sites and the articles are kept on the phone.

- Add a feed by its address, or by the address of its website (the feed is looked up).
- Import subscriptions from an OPML file (Documents, Downloads or SD card) or an OPML address;
  OPML folders become sections. Export writes `Documents/feedpond-feeds.opml`.
- Opens on one list with the articles of all feeds; swipe back for the list of feeds.
- Unread counts, "unread only" filter, mark as read/unread, article view with images.
- Feed icons (cached in `~/.cache/harbour/feedpond/icons`), article thumbnails, and articles
  scrolled past are marked as read; each can be switched off in Settings.
- "Open full article" reads the article's web page in the app (reader view: the element with
  the most prose wins, menus/ads/comments are dropped) and keeps it; or opens the browser.

## Layout

| Path | What |
|---|---|
| `qml/` | Silica UI (feeds, articles, article, add dialog, about) |
| `python/feedparse.py` | RSS/Atom/RDF and OPML parsing, feed discovery, article HTML cleaning |
| `python/store.py` | SQLite storage (`~/.local/share/harbour/feedpond/feeds.sqlite`) |
| `python/backend.py` | Downloads and the functions the UI calls through PyOtherSide |
| `tests/` | Engine tests with a local web server |

The engine uses the Python standard library only.

## Build and test

In WSL (`FedoraLinux-44`), from this folder:

```sh
python3 -B -m unittest discover -s tests
sh tools/build-rpm.sh        # -> RPMS/noarch/harbour-feedpond-*.noarch.rpm
```

## Not there yet

Background updates with notifications, starred articles, search,
editing a feed's name or folder, cleaning up old articles.
