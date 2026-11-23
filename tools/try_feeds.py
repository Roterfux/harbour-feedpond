"""Try the engine on real addresses (development only; needs a network connection).

    python3 tools/try_feeds.py https://example.org/ https://example.org/feed.xml ...
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

import backend  # noqa: E402

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        backend.init(os.path.join(tmp, "feeds.sqlite"), os.path.join(tmp, "cache"))
        for address in sys.argv[1:]:
            del backend.events[:]
            backend.subscribe(address)
            while ("busy", False, 0, 0) not in backend.events:
                time.sleep(0.05)
            print("%-45s %s" % (address, [e[1] for e in backend.events if e[0] == "notice"]))
        for feed in backend.feeds():
            icon = feed["icon"]
            print("\n%s  <%s>  icon: %s" % (feed["title"], feed["url"], "%s, %d bytes" % (
                os.path.splitext(icon)[1], os.path.getsize(icon)) if icon else "none"))
            rows = backend.items(feed["fid"], limit=500)
            print("   %d of %d articles have a picture" % (
                len([r for r in rows if r["image"]]), len(rows)))
            for row in rows[:2]:
                article = backend.open_item(row["iid"], 500)
                kinds = [b["kind"] for b in article["blocks"]]
                print("   %s | %s | %d blocks, %d images, %d videos | %s" % (
                    time.strftime("%Y-%m-%d %H:%M", time.gmtime(row["published"])),
                    row["title"][:50], len(kinds), kinds.count("image"),
                    kinds.count("video") + kinds.count("embed"), row["image"][:60]))
        backend.store.close()
