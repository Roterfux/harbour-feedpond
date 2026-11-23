# Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
"""The subscriptions and their articles in one SQLite file."""
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS feeds (
    id       INTEGER PRIMARY KEY,
    url      TEXT NOT NULL UNIQUE,
    title    TEXT NOT NULL DEFAULT '',
    site     TEXT NOT NULL DEFAULT '',
    tag      TEXT NOT NULL DEFAULT '',
    etag     TEXT NOT NULL DEFAULT '',
    modified TEXT NOT NULL DEFAULT '',
    error    TEXT NOT NULL DEFAULT '',
    updated  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS items (
    id        INTEGER PRIMARY KEY,
    feed_id   INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    guid      TEXT NOT NULL,
    title     TEXT NOT NULL DEFAULT '',
    link      TEXT NOT NULL DEFAULT '',
    author    TEXT NOT NULL DEFAULT '',
    published INTEGER NOT NULL DEFAULT 0,
    summary   TEXT NOT NULL DEFAULT '',
    content   TEXT NOT NULL DEFAULT '',
    read      INTEGER NOT NULL DEFAULT 0,
    UNIQUE (feed_id, guid)
);
CREATE TABLE IF NOT EXISTS gone (
    feed_id  INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    guid     TEXT NOT NULL,
    PRIMARY KEY (feed_id, guid)
);
CREATE INDEX IF NOT EXISTS items_by_date ON items (published DESC, id DESC);
CREATE INDEX IF NOT EXISTS items_by_feed ON items (feed_id, read);
"""


KEEP = 25                    # articles kept per feed, the newest


class Store:
    """All methods may be called from any thread."""

    def __init__(self, path, keep=KEEP):
        self.keep = keep
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        # Added after 0.1: databases made by 0.1 get the columns here
        self._column("feeds", "icon", "TEXT NOT NULL DEFAULT ''")        # cached file path
        self._column("feeds", "icon_checked", "INTEGER NOT NULL DEFAULT 0")
        self._column("items", "image", "TEXT NOT NULL DEFAULT ''")       # picture address
        self._column("items", "full", "TEXT NOT NULL DEFAULT ''")        # from the web page
        self._column("items", "video", "TEXT NOT NULL DEFAULT ''")       # enclosed video file
        self.db.commit()

    def _column(self, table, name, definition):
        have = [row["name"] for row in self.db.execute("PRAGMA table_info(%s)" % table)]
        if name not in have:
            self.db.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, definition))

    def close(self):
        with self.lock:
            self.db.close()

    def _rows(self, sql, args=()):
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, args)]

    # ------------------------------------------------------------ feeds

    def add_feed(self, url, title="", tag=""):
        """(feed id, True if it is new)."""
        with self.lock, self.db:
            row = self.db.execute("SELECT id FROM feeds WHERE url = ?", (url,)).fetchone()
            if row:
                return row["id"], False
            cur = self.db.execute("INSERT INTO feeds (url, title, tag) VALUES (?, ?, ?)",
                                  (url, title or "", tag or ""))
            return cur.lastrowid, True

    def feeds(self):
        return self._rows(
            "SELECT f.*, (SELECT COUNT(*) FROM items i WHERE i.feed_id = f.id AND i.read = 0)"
            " AS unread FROM feeds f"
            " ORDER BY f.tag COLLATE NOCASE, f.title COLLATE NOCASE, f.url")

    def feed(self, feed_id):
        rows = self._rows("SELECT * FROM feeds WHERE id = ?", (feed_id,))
        return rows[0] if rows else None

    def remove_feed(self, feed_id):
        with self.lock, self.db:
            self.db.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))

    def set_error(self, feed_id, message):
        with self.lock, self.db:
            self.db.execute("UPDATE feeds SET error = ?, updated = ? WHERE id = ?",
                            (message, int(time.time()), feed_id))

    def set_icon(self, feed_id, path, now=None):
        """Remember the icon file ("" = none found; looked for at `now`)."""
        with self.lock, self.db:
            self.db.execute("UPDATE feeds SET icon = ?, icon_checked = ? WHERE id = ?",
                            (path or "", int(now or time.time()), feed_id))

    def version(self):
        """A counter the engine uses for one-time upgrade steps."""
        with self.lock:
            return self.db.execute("PRAGMA user_version").fetchone()[0]

    def set_version(self, number):
        with self.lock, self.db:
            self.db.execute("PRAGMA user_version = %d" % int(number))

    def forget_icon_checks(self):
        """Feeds without an icon may be looked up again at once."""
        with self.lock, self.db:
            self.db.execute("UPDATE feeds SET icon_checked = 0 WHERE icon = ''")

    def mark_checked(self, feed_id):
        """The server said "not modified"."""
        self.set_error(feed_id, "")

    def prune(self, feed_id=0):
        """Drop all but the newest `keep` articles of a feed (0: of every feed). Their ids
        are remembered, so that a feed still listing them does not bring them back."""
        with self.lock, self.db:
            ids = [feed_id] if feed_id else [
                row[0] for row in self.db.execute("SELECT id FROM feeds")]
            for one in ids:
                self._prune(one)

    def _prune(self, feed_id):
        old = self.db.execute(
            "SELECT id, guid FROM items WHERE feed_id = ?"
            " ORDER BY published DESC, id DESC LIMIT -1 OFFSET ?",
            (feed_id, self.keep)).fetchall()
        self.db.executemany("INSERT OR IGNORE INTO gone (feed_id, guid) VALUES (?, ?)",
                            [(feed_id, row["guid"]) for row in old])
        self.db.executemany("DELETE FROM items WHERE id = ?", [(row["id"],) for row in old])

    def save_result(self, feed_id, parsed, etag="", modified="", now=None):
        """Store a parsed feed and keep its newest articles; returns how many are new."""
        now = int(now or time.time())
        added = []
        with self.lock, self.db:
            gone = {row[0] for row in self.db.execute(
                "SELECT guid FROM gone WHERE feed_id = ?", (feed_id,))}
            self.db.execute(
                "UPDATE feeds SET title = CASE WHEN title = '' THEN ? ELSE title END,"
                " site = CASE WHEN ? != '' THEN ? ELSE site END,"
                " etag = ?, modified = ?, error = '', updated = ? WHERE id = ?",
                (parsed.get("title") or "", parsed.get("site") or "", parsed.get("site") or "",
                 etag or "", modified or "", now, feed_id))
            # Oldest first: among articles without a usable date the newest gets the
            # highest id and so sorts first.
            for item in reversed(parsed.get("items", [])):
                if item["guid"] in gone:              # dropped before as too old
                    continue
                published = item.get("published") or 0
                if published <= 0 or published > now + 86400:
                    published = now
                cur = self.db.execute(
                    "INSERT OR IGNORE INTO items"
                    " (feed_id, guid, title, link, author, published, summary, content, image,"
                    " video) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (feed_id, item["guid"], item.get("title") or "", item.get("link") or "",
                     item.get("author") or "", published, item.get("summary") or "",
                     item.get("content") or "", item.get("image") or "",
                     item.get("video") or ""))
                if cur.rowcount:
                    added.append(cur.lastrowid)
                if not cur.rowcount and item.get("image"):
                    # Known article stored before pictures were kept
                    self.db.execute("UPDATE items SET image = ? WHERE feed_id = ? AND guid = ?"
                                    " AND image = ''", (item["image"], feed_id, item["guid"]))
                if not cur.rowcount and item.get("video"):
                    self.db.execute("UPDATE items SET video = ? WHERE feed_id = ? AND guid = ?"
                                    " AND video = ''", (item["video"], feed_id, item["guid"]))
            self._prune(feed_id)
            # Forget dropped articles the feed no longer lists: they cannot come back
            listed = [item["guid"] for item in parsed.get("items", [])]
            if listed:
                self.db.execute("DELETE FROM gone WHERE feed_id = ? AND guid NOT IN (%s)"
                                % ",".join("?" * len(listed)), [feed_id] + listed)
            if not added:
                return 0
            return self.db.execute("SELECT COUNT(*) FROM items WHERE id IN (%s)"
                                   % ",".join("?" * len(added)), added).fetchone()[0]

    # ------------------------------------------------------------ articles

    def items(self, feed_id=0, unread_only=False, limit=60, before_published=0, before_id=0):
        """Newest first. For the next page pass the last row's published and id."""
        where, args = [], []
        if feed_id:
            where.append("i.feed_id = ?")
            args.append(feed_id)
        if unread_only:
            where.append("i.read = 0")
        if before_id:
            where.append("(i.published < ? OR (i.published = ? AND i.id < ?))")
            args += [before_published, before_published, before_id]
        sql = ("SELECT i.id, i.feed_id, i.title, i.link, i.published, i.summary, i.read, i.image,"
               " CASE WHEN f.title != '' THEN f.title ELSE f.url END AS feed,"
               " f.icon AS feed_icon"
               " FROM items i JOIN feeds f ON f.id = i.feed_id")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY i.published DESC, i.id DESC LIMIT ?"
        return self._rows(sql, args + [int(limit)])

    def item(self, item_id):
        rows = self._rows(
            "SELECT i.*, CASE WHEN f.title != '' THEN f.title ELSE f.url END AS feed,"
            " f.icon AS feed_icon FROM items i JOIN feeds f ON f.id = i.feed_id WHERE i.id = ?", (item_id,))
        return rows[0] if rows else None

    def unread_articles(self):
        """The unread articles with everything offline reading needs, newest first."""
        return self._rows("SELECT * FROM items WHERE read = 0 ORDER BY published DESC, id DESC")

    def forget_full(self):
        with self.lock, self.db:
            self.db.execute("UPDATE items SET full = '' WHERE full != ''")

    def set_full(self, item_id, markup):
        """Keep the article text read from its web page."""
        with self.lock, self.db:
            self.db.execute("UPDATE items SET full = ? WHERE id = ?", (markup or "", item_id))

    def set_read(self, item_id, read=True):
        with self.lock, self.db:
            self.db.execute("UPDATE items SET read = ? WHERE id = ?",
                            (1 if read else 0, item_id))

    def set_read_many(self, item_ids, read=True):
        with self.lock, self.db:
            self.db.executemany("UPDATE items SET read = ? WHERE id = ?",
                                [(1 if read else 0, int(i)) for i in item_ids])

    def mark_all_read(self, feed_id=0):
        with self.lock, self.db:
            if feed_id:
                self.db.execute("UPDATE items SET read = 1 WHERE read = 0 AND feed_id = ?",
                                (feed_id,))
            else:
                self.db.execute("UPDATE items SET read = 1 WHERE read = 0")

    def unread_total(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM items WHERE read = 0").fetchone()[0]
