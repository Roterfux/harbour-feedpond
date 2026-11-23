"""Off-device tests of the engine: python -m unittest discover -s tests -v"""
import http.server
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

import backend      # noqa: E402
import feedparse    # noqa: E402
from store import Store  # noqa: E402

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:media="http://search.yahoo.com/mrss/">
<channel>
  <title>Pond &amp; News</title>
  <atom:link href="http://example.org/feed.xml" rel="self" type="application/rss+xml"/>
  <link>http://example.org/</link>
  <item>
    <title>Second &lt;b&gt;post&lt;/b&gt;</title>
    <link>/posts/2</link>
    <guid isPermaLink="false">post-2</guid>
    <pubDate>Mon, 09 Nov 2026 10:00:00 +0100</pubDate>
    <dc:creator>Ada</dc:creator>
    <media:content url="http://example.org/a.jpg"/>
    <description>Short text</description>
    <content:encoded><![CDATA[<p>Full <b>text</b></p><script>alert(1)</script>]]></content:encoded>
  </item>
  <item>
    <title>First post</title>
    <guid>http://example.org/posts/1</guid>
    <pubDate>Sun, 08 Nov 2026 09:00:00 GMT</pubDate>
    <description>&lt;p&gt;Hello&lt;/p&gt;</description>
  </item>
</channel>
</rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title type="text">Atom pond</title>
  <link rel="self" href="http://example.net/atom.xml"/>
  <link href="http://example.net/"/>
  <entry>
    <title>Entry one</title>
    <id>tag:example.net,2026:1</id>
    <link rel="replies" href="http://example.net/1/comments"/>
    <link rel="alternate" type="text/html" href="1.html"/>
    <updated>2026-11-09T12:30:00.123Z</updated>
    <published>2026-11-09T08:00:00+02:00</published>
    <author><name>Grace</name><email>g@example.net</email></author>
    <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml"><p>Rich <em>text</em></p></div></content>
  </entry>
  <entry>
    <title>Entry two</title>
    <id>tag:example.net,2026:2</id>
    <summary>1 &lt; 2</summary>
  </entry>
</feed>"""

RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="http://example.com/"><title>RDF pond</title><link>http://example.com/</link></channel>
  <item rdf:about="http://example.com/a"><title>A</title><link>http://example.com/a</link>
    <dc:date>2026-11-01</dc:date></item>
</rdf:RDF>"""

SLOPPY = b"""\n\n<?xml version="1.0" encoding="iso-8859-1"?>
<rss version="2.0"><channel><title>Caf\xe9 & bar</title>
<item><title>Fish&nbsp;&amp;&nbsp;chips &copy; R&D</title><link>http://example.org/x?a=1&b=2</link></item>
</channel></rss>"""

OPML = b"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.1"><head><title>subs</title></head><body>
  <outline text="Loose" type="rss" xmlUrl="http://example.org/feed.xml" htmlUrl="http://example.org/"/>
  <outline text="Tech" title="Tech">
    <outline title="Atom pond" type="rss" xmlurl="http://example.net/atom.xml"/>
    <outline text="Sub folder">
      <outline text="Deep" xmlUrl="https://example.com/deep & more"/>
    </outline>
    <outline text="Duplicate" xmlUrl="http://example.org/feed.xml"/>
    <outline text="Not a feed" xmlUrl="ftp://example.org/x"/>
  </outline>
</body></opml>"""

PAGE = b"""<!DOCTYPE html><html><head><title>Site</title>
<link rel="stylesheet" href="/s.css"><link rel="icon" sizes="96x96" href="/icon.png">
<link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml">
<link rel="alternate" type="application/atom+xml" href="http://example.net/atom.xml">
</head><body><p>Hi</p></body></html>"""


ARTICLE = """<!DOCTYPE html><html><head><title>Big story - Site</title>
<meta property="og:image" content="/lead.jpg"><script>var x = "<p>no</p>";</script></head>
<body><header class="site-header"><a href="/">Site</a> <ul class="menu"><li><a href="/a">A</a>
</li><li><a href="/b">B</a></li></ul></header>
<nav><p>Home, News, Sports, Weather, and many, many, more sections of the site</p></nav>
<div id="main"><article class="post">
<h1>Big story</h1>
<p>The first paragraph of the story, long enough to count, with commas, and more words in it.
<p>The second paragraph goes on, telling what happened, where, when, and why it matters.
<img data-src="pics/one.jpg" src="data:image/gif;base64,R0lGOD" width="800" height="400">
<p>Café owners said so. A third paragraph, with a <a href="/more">link</a> inside.</p>
<div class="share-buttons"><p>Share this on social media, everyone, right now, please</p></div>
</article>
<aside class="sidebar"><p>Read also: other stories, other news, other things, other days.</p>
</aside>
<div class="comments"><p>First comment, with, many, commas, to, tempt, the, scorer, here.</p>
</div></div><footer><p>Copyright, all rights reserved, imprint, privacy, terms.</p></footer>
</body></html>""".encode("utf-8")


class ParseTests(unittest.TestCase):
    def test_full_article(self):
        found = feedparse.extract_article(ARTICLE, "http://example.org/news/big", "Big story")
        text = feedparse.plain(found["markup"])
        self.assertIn("The first paragraph", text)
        self.assertIn("Café owners said so", text)
        for unwanted in ("Home, News", "Share this", "Read also", "First comment",
                         "Copyright", "no</p>", "Big story"):
            self.assertNotIn(unwanted, found["markup"])
        self.assertIn('src="http://example.org/news/pics/one.jpg"', found["markup"])
        self.assertIn('href="http://example.org/more"', found["markup"])
        self.assertNotIn("lead.jpg", found["markup"])      # the text has a picture itself
        self.assertGreater(found["length"], 200)
        self.assertEqual(found["title"], "Big story - Site")
        # The whole page in a block whose class name sounds like a sidebar (as on BBC News)
        wrapped = ARTICLE.replace(b'<div id="main">', b'<div class="ContainerWithSidebar">')
        found = feedparse.extract_article(wrapped, "http://example.org/news/big", "Big story")
        self.assertIn("The second paragraph", found["markup"])
        self.assertNotIn("Share this", found["markup"])
        # Without a picture in the text, the page's main picture leads it
        bare = ARTICLE.replace(b'<img data-src="pics/one.jpg"', b'<b data-src=""')
        found = feedparse.extract_article(bare, "http://example.org/news/big")
        self.assertTrue(found["markup"].startswith('<img src="http://example.org/lead.jpg">'))
        self.assertIn("<h1>Big story</h1>", found["markup"])   # no title given: kept
        # Other encodings and pages without any article
        latin = ARTICLE.decode("utf-8").replace("<title>", '<meta charset="iso-8859-1"><title>')
        found = feedparse.extract_article(latin.encode("iso-8859-1"), "http://example.org/")
        self.assertIn("Café owners", feedparse.plain(found["markup"]))
        self.assertLess(feedparse.extract_article(b"<html><body>Hi</body></html>")["length"], 10)
        deep = b"<div>" * 5000 + b"<p>" + b"word, " * 100 + b"</p>"
        self.assertGreater(feedparse.extract_article(deep)["length"], 500)

    def test_article_without_paragraph_tags(self):
        # As on winfuture.de: text between <br>s, an author box with real <p>s, a link list
        text = "<br><br>".join("Line %d of the story goes on, with commas, and enough words "
                               "to look like prose, again and again." % n for n in range(8))
        page = ('<html><body><div id="wrap"><div class="content_wrap"><h1>T</h1>'
                '<div id="news_content">%s<h2>More</h2>Final words of the story, with a comma, '
                'with a <a href="/in">link in the text</a>, here.<br><br>'
                '<a class="button_box red" rel="sponsored nofollow" href="/shop"><span>'
                '<strong>Game</strong><span>Jetzt vorbestellen</span></span><span>'
                '<span class="css_button">Zum Angebot</span></span></a><br>'
                '<a rel="sponsored" href="/aff">plain affiliate link</a><br>'
                '<b>Siehe auch:</b><br><ul><li><a href="/1">Other story one</a></li>'
                '<li><a href="/2">Other story two</a></li></ul></div></div>'
                '<div class="wf-autorbox"><p>Jane Doe, writer since 2001, about Windows, '
                'networks, and many other things.</p></div>'
                '<div id="right">%s</div></div></body></html>' % (
                    text, "<p><a href='/x'>Teaser, teaser, teaser, teaser, teaser</a></p>" * 5))
        found = feedparse.extract_article(page.encode(), "http://e.org/")
        markup = found["markup"]
        self.assertIn("Line 0 of the story", markup)
        self.assertIn("Final words", markup)
        self.assertIn('<a href="http://e.org/in">link in the text</a>', markup)
        self.assertIn("plain affiliate link", markup)       # a link in the text stays
        for unwanted in ("Jane Doe", "Other story", "Teaser", "Zum Angebot", "vorbestellen",
                         "Siehe auch"):
            self.assertNotIn(unwanted, markup)

    def test_article_from_structured_data(self):
        body = " ".join("Sentence %d tells a part of the news, as it is." % n for n in range(40))
        page = ('<html><head><script type="application/ld+json">{"@graph": [{"@type": '
                '"WebPage"}, {"@type": "NewsArticle", "articleBody": "%s"}]}</script>'
                '<meta property="og:image" content="/lead.jpg"></head><body>'
                '<p>Please allow ads, or subscribe, to read this, thank you.</p></body></html>'
                % body)
        found = feedparse.extract_article(page.encode(), "http://e.org/a")
        self.assertTrue(found["markup"].startswith('<img src="http://e.org/lead.jpg"><p>'
                                                   'Sentence 0 tells'))
        self.assertGreater(found["markup"].count("<p>"), 3)          # cut into paragraphs
        self.assertIn("Sentence 39", found["markup"])
        self.assertNotIn("allow ads", found["markup"])
        self.assertEqual(feedparse._text_markup("One.\n\nTwo &amp; three."),
                         "<p>One.</p><p>Two &amp; three.</p>")

    def test_srcset_pictures(self):
        img = {"src": "data:x", "srcset": "s.jpg 320w, m.jpg 800w, l.jpg 1600w"}
        self.assertEqual(feedparse._picture(img, "http://a.org/"), "http://a.org/m.jpg")
        img = {"srcset": "s.jpg 100w, l.jpg 400w"}
        self.assertEqual(feedparse._picture(img, "http://a.org/"), "http://a.org/l.jpg")
        img = {"srcset": "s.jpg 320w, m.jpg 500w, l.jpg 1600w"}       # small but enough
        self.assertEqual(feedparse._picture(img, "http://a.org/"), "http://a.org/m.jpg")
        # A feed with several sizes of a picture: the smallest wide enough one
        feed = feedparse.parse_feed(
            b'<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>p</title>'
            b'<media:content url="http://e.org/big.jpg" medium="image" width="1920"/>'
            b'<media:content url="http://e.org/mid.jpg" medium="image" width="640"/>'
            b'<media:thumbnail url="http://e.org/tiny.jpg" width="140"/>'
            b'</item></channel></rss>')
        self.assertEqual(feed["items"][0]["image"], "http://e.org/mid.jpg")


    def test_rss(self):
        feed = feedparse.parse_feed(RSS, "http://example.org/feed.xml")
        self.assertEqual(feed["title"], "Pond & News")
        self.assertEqual(feed["site"], "http://example.org/")
        second, first = feed["items"]
        self.assertEqual(second["title"], "Second post")
        self.assertEqual(second["link"], "http://example.org/posts/2")
        self.assertEqual(second["guid"], "post-2")
        self.assertEqual(second["author"], "Ada")
        self.assertIn("<p>Full <b>text</b></p>", second["content"])
        self.assertEqual(second["summary"], "Full text")
        self.assertEqual(second["published"], 1794214800)     # 09:00 UTC
        self.assertEqual(second["image"], "http://example.org/a.jpg")   # media:content
        self.assertEqual(first["image"], "")
        self.assertEqual(feed["icon"], "")
        self.assertEqual(first["link"], "http://example.org/posts/1")
        self.assertEqual(first["content"], "<p>Hello</p>")
        self.assertEqual(first["published"], 1794214800 - 86400)

    def test_atom(self):
        feed = feedparse.parse_feed(ATOM, "http://example.net/atom.xml")
        self.assertEqual(feed["title"], "Atom pond")
        self.assertEqual(feed["site"], "http://example.net/")
        one, two = feed["items"]
        self.assertEqual(one["link"], "http://example.net/1.html")
        self.assertEqual(one["author"], "Grace")
        self.assertEqual(one["published"], 1794204000)        # 06:00 UTC, not "updated"
        self.assertIn("Rich", one["content"])
        self.assertIn("Rich text", feedparse.plain(feedparse.clean_html(one["content"])))
        self.assertEqual(two["content"], "1 &lt; 2")          # text summary is escaped
        self.assertEqual(two["published"], 0)
        self.assertEqual(two["link"], "")

    def test_rdf(self):
        feed = feedparse.parse_feed(RDF)
        self.assertEqual(feed["title"], "RDF pond")
        self.assertEqual(len(feed["items"]), 1)
        self.assertEqual(feed["items"][0]["published"], 1793491200)

    def test_sloppy_xml_is_repaired(self):
        feed = feedparse.parse_feed(SLOPPY)
        self.assertEqual(feed["title"], "Café & bar")
        self.assertEqual(feed["items"][0]["title"], "Fish & chips © R&D".replace(" ", " "))
        self.assertEqual(feed["items"][0]["link"], "http://example.org/x?a=1&b=2")

    def test_rejects_non_feeds(self):
        with self.assertRaises(feedparse.FeedError):
            feedparse.parse_feed(b"<html><body>no</body></html>")
        with self.assertRaises(feedparse.FeedError):
            feedparse.parse_feed(b"just text")
        with self.assertRaises(feedparse.FeedError):
            feedparse.parse_feed(b'<!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel/></rss>')

    def test_dates(self):
        d = feedparse.parse_date
        self.assertEqual(d("2026-11-09T09:00:00Z"), 1794214800)
        self.assertEqual(d("2026-11-09T10:00:00+01:00"), 1794214800)
        self.assertEqual(d("2026-11-09 04:00:00.5 -0500"), 1794214800)
        self.assertEqual(d("Mon, 09 Nov 2026 09:00:00 GMT"), 1794214800)
        self.assertEqual(d("9 Nov 2026 09:00 +0000"), 1794214800)
        self.assertEqual(d("yesterday"), 0)
        self.assertEqual(d("2026-13-40"), 0)
        self.assertEqual(d(""), 0)

    def test_opml(self):
        subs = feedparse.parse_opml(OPML)
        self.assertEqual([(s["url"], s["title"], s["tag"]) for s in subs], [
            ("http://example.org/feed.xml", "Loose", ""),
            ("http://example.net/atom.xml", "Atom pond", "Tech"),
            ("https://example.com/deep & more", "Deep", "Sub folder"),
        ])
        with self.assertRaises(feedparse.FeedError):
            feedparse.parse_opml(RSS)

    def test_opml_round_trip(self):
        subs = feedparse.parse_opml(OPML)
        for s in subs:
            s["site"] = 'http://site/?a="1"&b=<2>'
        again = feedparse.parse_opml(feedparse.build_opml(subs))
        # (the export sorts the folders by name)
        self.assertEqual(sorted((s["url"], s["title"], s["tag"]) for s in again),
                         sorted((s["url"], s["title"], s["tag"]) for s in subs))

    def test_discover_and_classify(self):
        links = ["http://example.org/feed.xml", "http://example.net/atom.xml"]
        self.assertEqual(feedparse.discover(PAGE, "http://example.org/blog/"), links)
        self.assertEqual(feedparse.classify(PAGE, "http://example.org/"), ("html", links))
        self.assertEqual(feedparse.classify(RSS)[0], "feed")
        self.assertEqual(feedparse.classify(ATOM)[0], "feed")
        self.assertEqual(feedparse.classify(b"\xef\xbb\xbf" + OPML)[0], "opml")
        self.assertEqual(feedparse.classify(b"%PDF-1.4 ...")[0], "unknown")
        self.assertEqual(feedparse.classify(b"<p>fragment <html> late")[0], "html")

    def test_article_pictures(self):
        feed = feedparse.parse_feed(b"""<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
          <channel><title>P</title><image><url>/logo.png</url></image>
          <item><title>sizes</title><link>http://example.org/p/1</link>
            <media:content url="http://i/140.jpg" width="140" type="image/jpeg"/>
            <media:content url="http://i/460.jpg" width="460" type="image/jpeg"/>
            <media:content url="http://i/clip.mp4" width="900" type="video/mp4"/></item>
          <item><title>thumb</title><media:group><media:thumbnail url="/t.jpg"/></media:group></item>
          <item><title>enclosure</title><enclosure url="http://i/e.png" type="image/png" length="1"/>
            <enclosure url="http://i/pod.mp3" type="audio/mpeg" length="1"/></item>
          <item><title>text</title><link>http://example.org/p/4</link><description>
            &lt;img src="http://t/pixel.gif" width="1" height="1"&gt;
            &lt;img class="emoji" src="http://e/1.png"&gt;&lt;img src="pic.jpg"&gt;</description></item>
          <item><title>none</title><enclosure url="http://i/pod.mp3" type="audio/mpeg"/></item>
          </channel></rss>""", "http://example.org/feed.xml")
        self.assertEqual(feed["icon"], "http://example.org/logo.png")
        self.assertEqual([item["image"] for item in feed["items"]], [
            "http://i/460.jpg", "http://example.org/t.jpg", "http://i/e.png",
            "http://example.org/p/pic.jpg", ""])

    def test_site_icons(self):
        page = b"""<html><head><link rel="shortcut icon" href="/favicon.ico">
            <link rel="icon" type="image/svg+xml" href="/i.svg">
            <link rel="icon" sizes="32x32" href="/32.png"><link rel="icon" sizes="96x96" href="/96.png">
            <link rel="apple-touch-icon" href="touch.png"><link rel="stylesheet" href="/s.css">"""
        self.assertEqual(feedparse.icons(page, "http://example.org/blog/"), [
            "http://example.org/96.png", "http://example.org/blog/touch.png",
            "http://example.org/32.png", "http://example.org/favicon.ico"])

    def test_clean_html(self):
        dirty = ('<div class="x" onclick="evil()"><p style="color:red">Hi <b>there</b></p>'
                 '<script>alert("x")</script><style>p{}</style><iframe src="http://x/"></iframe>'
                 '<a href="/more" onmouseover="x()">more</a> <a href="javascript:alert(1)">bad</a>'
                 '<img src="/big.jpg" onerror="x()"><img src="http://t/p.gif" width="1" height="1">'
                 '<img src="s.png" width="40" height="20">'
                 '<img class="wp-smiley" alt=":)" src="http://e/smile.png">'
                 '<img src="data:image/gif;base64,AAAA" data-src="lazy.jpg">'
                 '<table><tr><td>a</td><td>b &lt; c</td></tr></table></div>')
        out = feedparse.clean_html(dirty, "http://example.org/post/1", 500)
        for bad in ("script", "alert", "style", "iframe", "onclick", "onerror", "onmouseover",
                    "javascript", "p.gif", "smile.png", "data:", "class"):
            self.assertNotIn(bad, out)
        self.assertIn("<p>Hi <b>there</b></p>", out)
        self.assertIn('<a href="http://example.org/more">more</a>', out)
        self.assertIn("<a>bad</a>", out)
        self.assertIn('<img src="http://example.org/big.jpg" width="500">', out)
        self.assertIn('<img src="http://example.org/post/s.png" width="40" height="20">', out)
        self.assertIn('<img src="http://example.org/post/lazy.jpg" width="500">', out)
        self.assertIn(":)", out)
        self.assertIn("b &lt; c", out)
        self.assertEqual(feedparse.clean_html(None), "")

    def test_article_blocks(self):
        markup = ('<p>Intro <b>bold <a href="/x">link<img src="/pic.jpg" width="640"></a> '
                  'after</b> end</p><p>Icon <img src="i.png" width="16" height="16"></p>'
                  '<video poster="/p.jpg"><source src="/v.webm" type="video/webm">old</video>'
                  '<iframe src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?x=1"></iframe>'
                  '<iframe src="https://ads.example/x"></iframe>'
                  '<p>Vimeo:</p><iframe data-src="//player.vimeo.com/video/123456"></iframe>')
        blocks = feedparse.article_blocks(markup, "http://e.org/a/", 400)
        self.assertEqual([b["kind"] for b in blocks],
                         ["text", "image", "text", "video", "embed", "text", "embed"])
        # Tags open at the picture are closed before it and opened again after it
        self.assertEqual(blocks[0]["html"],
                         '<p>Intro <b>bold <a href="http://e.org/x">link</a></b></p>')
        self.assertEqual(blocks[1], {"kind": "image", "src": "http://e.org/pic.jpg",
                                     "width": 640, "height": 0, "link": "http://e.org/x"})
        self.assertTrue(blocks[2]["html"].startswith(
            '<p><b><a href="http://e.org/x"></a> after</b> end</p><p>Icon <img src='))
        self.assertEqual(blocks[3], {"kind": "video", "src": "http://e.org/v.webm",
                                     "poster": "http://e.org/p.jpg"})
        self.assertEqual(blocks[4]["url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertIn("ytimg.com/vi/dQw4w9WgXcQ/", blocks[4]["poster"])
        self.assertEqual(blocks[4]["play"], "https://m.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(blocks[6]["url"], "https://vimeo.com/123456")
        self.assertEqual(blocks[6]["play"], "https://player.vimeo.com/video/123456?autoplay=1")
        self.assertNotIn("old<", str(blocks))           # the <video> fallback text
        self.assertEqual(feedparse.article_blocks(""), [])
        # One markup string (no blocks): videos become links
        self.assertIn('<a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ">YouTube</a>',
                      feedparse.clean_html(markup))
        self.assertEqual(feedparse.video_link("https://youtu.be/dQw4w9WgXcQ")["site"], "YouTube")
        self.assertIsNone(feedparse.video_link("https://example.org/watch?v=1"))
        # A YouTube article without a picture gets the video's in the lists
        row = {"image": "", "link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
        self.assertIn("i.ytimg.com/vi/dQw4w9WgXcQ/", backend._row_image(row))
        self.assertEqual(backend._row_image({"image": "x.jpg", "link": row["link"]}), "x.jpg")
        # A video the feed encloses takes the place of its own picture in the text
        item = {"link": "http://e.org/1", "video": "http://e.org/v.mp4",
                "image": "http://e.org/p.jpg"}
        blocks = backend._blocks(item, '<p>Hi</p><img src="/p.jpg">', 400)
        self.assertEqual([b["kind"] for b in blocks], ["video", "text"])

    def test_speech_text(self):
        blocks = [{"kind": "text", "html": "<h2>Heading</h2><p>First <b>part</b>.</p>"
                                            "<ul><li>Point one</li></ul>Line<br>Next?"},
                  {"kind": "image", "src": "x"},
                  {"kind": "text", "html": "<p>Café &amp; more “quoted”</p>"}]
        self.assertEqual(backend.speech_text("A &amp; B", blocks),
                         "A & B.\nHeading.\nFirst part.\nPoint one.\nLine.\nNext?\n"
                         "Café & more “quoted”")
        self.assertEqual(backend.speech_text("", []), "")

    def test_reading_minutes(self):
        def text(words):
            return {"kind": "text", "html": "<p>%s</p>" % " ".join(["word"] * words)}
        self.assertEqual(backend.reading_minutes([]), 1)                    # at least one
        self.assertEqual(backend.reading_minutes([text(20)]), 1)
        self.assertEqual(backend.reading_minutes([text(1000)]), 5)          # 200 words a minute
        self.assertEqual(backend.reading_minutes([text(600), text(300)]), 5)  # 4.5 rounds up
        picture = {"kind": "image", "src": "x"}
        self.assertEqual(backend.reading_minutes([text(400)] + [picture] * 6), 3)

    def test_video_enclosure(self):
        feed = feedparse.parse_feed(
            b'<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>v</title>'
            b'<link>http://e.org/1</link><media:content url="/clip.mp4" medium="video"/>'
            b'</item><item><title>a</title><enclosure url="http://e.org/a.mp3" '
            b'type="audio/mpeg"/></item></channel></rss>', "http://e.org/")
        self.assertEqual([i["video"] for i in feed["items"]], ["http://e.org/clip.mp4", ""])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_feeds_and_articles(self):
        fid, created = self.store.add_feed("http://example.org/feed.xml", "", "Tech")
        self.assertTrue(created)
        self.assertEqual(self.store.add_feed("http://example.org/feed.xml"), (fid, False))
        parsed = feedparse.parse_feed(RSS, "http://example.org/feed.xml")
        self.assertEqual(self.store.save_result(fid, parsed, "etag-1", "", now=1794300000), 2)
        self.assertEqual(self.store.save_result(fid, parsed, now=1794300000), 0)   # no duplicates
        feed = self.store.feeds()[0]
        self.assertEqual((feed["title"], feed["unread"], feed["tag"]), ("Pond & News", 2, "Tech"))
        rows = self.store.items()
        self.assertEqual([r["title"] for r in rows], ["Second post", "First post"])
        self.assertEqual(rows[0]["feed"], "Pond & News")
        self.store.set_read(rows[0]["id"])
        self.assertEqual(self.store.unread_total(), 1)
        self.assertEqual([r["title"] for r in self.store.items(unread_only=True)], ["First post"])
        self.assertIn("Full", self.store.item(rows[0]["id"])["content"])
        self.store.mark_all_read(fid)
        self.assertEqual(self.store.unread_total(), 0)
        self.store.remove_feed(fid)
        self.assertEqual(self.store.items(), [])       # articles go with their feed

    def test_database_from_version_0_1_is_upgraded(self):
        import sqlite3
        from store import SCHEMA
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "old.sqlite")
            old = sqlite3.connect(path)
            old.executescript(SCHEMA)          # the 0.1 tables, without icon and image
            old.execute("INSERT INTO feeds (url) VALUES ('http://example.org/feed.xml')")
            old.execute("INSERT INTO items (feed_id, guid, title) VALUES (1, 'post-2', 'Old')")
            old.commit()
            old.close()
            store = Store(path)
            self.assertEqual(store.feeds()[0]["icon"], "")
            store.save_result(1, feedparse.parse_feed(RSS, "http://example.org/feed.xml"))
            rows = {r["title"]: r for r in store.items()}
            self.assertEqual(rows["Old"]["image"], "http://example.org/a.jpg")   # filled in later
            store.set_read_many([r["id"] for r in rows.values()])
            self.assertEqual(store.unread_total(), 0)
            store.close()

    def test_title_from_opml_is_kept(self):
        fid, _ = self.store.add_feed("http://example.org/feed.xml", "My name")
        self.store.save_result(fid, feedparse.parse_feed(RSS))
        self.assertEqual(self.store.feed(fid)["title"], "My name")

    def test_paging_and_undated_articles(self):
        fid, _ = self.store.add_feed("http://example.org/many.xml")
        entries = [{"guid": "g%d" % n, "title": "T%d" % n, "published": 0} for n in range(25)]
        entries[3]["published"] = 99999999999        # far in the future: treated as "now"
        self.store.save_result(fid, {"title": "Many", "items": entries}, now=1000000)
        seen, last = [], None
        while True:
            page = self.store.items(fid, limit=10,
                                    before_published=last["published"] if last else 0,
                                    before_id=last["id"] if last else 0)
            if not page:
                break
            seen += [r["title"] for r in page]
            last = page[-1]
        self.assertEqual(seen, ["T%d" % n for n in range(25)])      # the feed's own order

    def test_only_the_newest_are_kept(self):
        store = Store(":memory:", keep=3)
        self.addCleanup(store.close)
        fid, _ = store.add_feed("http://example.org/f.xml")
        other, _ = store.add_feed("http://example.org/g.xml")

        def entries(*numbers):
            return {"items": [{"guid": "g%d" % n, "title": "T%d" % n, "published": 1000 + n}
                              for n in numbers]}
        self.assertEqual(store.save_result(fid, entries(5, 4, 3, 2, 1), now=5000), 3)
        self.assertEqual([r["title"] for r in store.items(fid)], ["T5", "T4", "T3"])
        # The dropped ones do not come back while the feed still lists them
        self.assertEqual(store.save_result(fid, entries(6, 5, 4, 3, 2, 1), now=5000), 1)
        self.assertEqual([r["title"] for r in store.items(fid)], ["T6", "T5", "T4"])
        self.assertEqual(store.unread_total(), 3)
        # Each feed has its own limit; once the feed stops listing one, it is forgotten
        store.save_result(other, entries(1, 2), now=5000)
        self.assertEqual(len(store.items(other)), 2)
        store.save_result(fid, entries(6, 5), now=5000)
        gone = {r[0] for r in store.db.execute("SELECT guid FROM gone WHERE feed_id = ?", (fid,))}
        self.assertEqual(gone, set())
        # A database from before the limit is cut down at the start
        big = Store(":memory:", keep=25)
        self.addCleanup(big.close)
        fid, _ = big.add_feed("http://example.org/f.xml")
        big.save_result(fid, entries(*range(30)), now=5000)
        self.assertEqual(len(big.items(fid)), 25)
        big.keep = 10
        big.prune()
        self.assertEqual(len(big.items(fid)), 10)


class _Site(http.server.BaseHTTPRequestHandler):
    pages = {"/feed.xml": RSS, "/atom.xml": ATOM, "/": PAGE, "/subs.opml": None,
             "/broken.xml": b"<rss><channel><item>", "/text": b"hello",
             "/icon.png": b"\x89PNG\r\n\x1a\n" + b"\0" * 32, "/local.xml": None,
             "/bare.xml": None, "/favicon.ico": b"<html>not an icon</html>"}
    hits = []

    def do_GET(self):
        _Site.hits.append(self.path)
        body = self.pages.get(self.path, b"")
        if self.path not in self.pages:
            self.send_error(404)
            return
        if self.path == "/feed.xml" and self.headers.get("If-None-Match") == '"v1"':
            self.send_response(304)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("ETag", '"v1"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Site)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        _Site.pages["/subs.opml"] = (
            '<opml version="2.0"><body><outline text="News">'
            '<outline text="Renamed" xmlUrl="%s/feed.xml"/>'
            '<outline text="Atom" xmlUrl="%s/atom.xml"/>'
            '<outline text="Gone" xmlUrl="%s/missing.xml"/>'
            '<outline text="Broken" xmlUrl="%s/broken.xml"/>'
            '</outline></body></opml>' % ((cls.base,) * 4)).encode()
        _Site.pages["/local.xml"] = (
            '<rss><channel><title>Local</title><link>%s/</link>'
            '<item><title>x</title></item></channel></rss>' % cls.base).encode()
        _Site.pages["/bare.xml"] = (                 # its "website" announces no icon
            '<rss><channel><title>Bare</title><link>%s/text</link>'
            '<item><title>x</title></item></channel></rss>' % cls.base).encode()
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        backend.init(os.path.join(self.tmp.name, "feeds.sqlite"),
                     os.path.join(self.tmp.name, "cache"))
        backend.ICONS = False          # the fixtures name real sites: no requests to them
        del backend.events[:]
        del _Site.hits[:]

    def tearDown(self):
        backend.store.close()
        self.tmp.cleanup()

    def wait(self):
        """Until the running job reports busy = False; returns the notices."""
        deadline = time.time() + 20
        while ("busy", False, 0, 0) not in backend.events:
            self.assertLess(time.time(), deadline, "job did not finish: %r" % backend.events)
            time.sleep(0.02)
        time.sleep(0.05)
        notices = [e[1] for e in backend.events if e[0] == "notice"]
        self.assertEqual(backend.events[-1][0], "changed")
        del backend.events[:]
        return notices

    def wait_for(self, name):
        """Until an event of that name arrives; returns and removes it."""
        deadline = time.time() + 20
        while True:
            for event in list(backend.events):
                if event[0] == name:
                    backend.events.remove(event)
                    return event
            self.assertLess(time.time(), deadline, "no %s event: %r" % (name, backend.events))
            time.sleep(0.02)

    def test_subscribe_to_feed_address(self):
        self.assertTrue(backend.subscribe(self.base + "/feed.xml"))
        self.assertEqual(self.wait(), ["Added Pond & News (2 articles)"])
        feeds = backend.feeds()
        self.assertEqual((feeds[0]["title"], feeds[0]["unread"]), ("Pond & News", 2))
        rows = backend.items()
        self.assertEqual(rows[0]["title"], "Second post")
        article = backend.open_item(rows[0]["iid"], 400)
        self.assertNotIn("script", str(article["blocks"]))
        self.assertEqual(article["unread"], 1)
        self.assertEqual(backend.set_read(rows[0]["iid"], False), 2)

    def test_subscribe_to_website_finds_the_feed(self):
        backend.subscribe(self.base + "/")
        self.assertEqual(self.wait(), ["Added Pond & News (2 articles)"])
        self.assertEqual(backend.feeds()[0]["url"], self.base + "/feed.xml")
        backend.subscribe(self.base + "/")
        self.assertEqual(self.wait(), ["Pond & News is already in the list"])

    def test_bad_addresses(self):
        for address, text in (("/text", "This address is not a feed"),
                              ("/nothing", "The server answered 404 Not Found"),
                              ("/broken.xml", "This address is not a feed")):
            backend.subscribe(self.base + address)
            self.assertEqual(self.wait(), [text])
        backend.subscribe("file:///etc/passwd")
        self.assertEqual(self.wait(), ["Not a web address: file:///etc/passwd"])
        self.assertEqual(backend.feeds(), [])

    def test_opml_import_from_file_then_refresh(self):
        path = os.path.join(self.tmp.name, "subs.opml")
        with open(path, "wb") as handle:
            handle.write(_Site.pages["/subs.opml"])
        self.assertTrue(backend.import_opml("file://" + path if os.name != "nt" else path))
        self.assertEqual(self.wait(), ["4 feeds imported", "4 new articles, 2 feeds failed"])
        feeds = {f["title"]: f for f in backend.feeds()}
        self.assertEqual(sorted(feeds), ["Atom", "Broken", "Gone", "Renamed"])
        self.assertEqual(feeds["Renamed"]["tag"], "News")
        self.assertEqual(feeds["Renamed"]["unread"], 2)
        self.assertIn("404", feeds["Gone"]["error"])
        self.assertIn("XML", feeds["Broken"]["error"])
        # Importing again adds nothing; a refresh uses the ETag and finds nothing new
        backend.import_opml(path)
        self.assertEqual(self.wait(), ["0 feeds imported, 4 were already there"])
        del _Site.hits[:]
        backend.refresh()
        self.assertEqual(self.wait(), ["0 new articles, 2 feeds failed"])
        self.assertEqual(sorted(_Site.hits),
                         ["/atom.xml", "/broken.xml", "/feed.xml", "/missing.xml"])
        self.assertEqual(feeds["Renamed"]["unread"], 2)
        backend.refresh(feeds["Atom"]["fid"])
        self.assertEqual(self.wait(), ["0 new articles"])

    def test_opml_import_from_address_and_export(self):
        backend.subscribe(self.base + "/subs.opml")
        self.assertEqual(self.wait()[0], "4 feeds imported")
        path = backend.export_opml(self.tmp.name)
        with open(path, "rb") as handle:
            subs = feedparse.parse_opml(handle.read())
        self.assertEqual(len(subs), 4)
        self.assertEqual({s["tag"] for s in subs}, {"News"})
        backend.mark_all_read()
        self.assertEqual(backend.events[-1], ("changed", 0))

    def test_feed_icons(self):
        backend.ICONS = True
        backend.subscribe(self.base + "/local.xml")     # its website announces /icon.png
        self.wait()
        # A site without any icon: neither the feed's page nor the front page names one,
        # and /favicon.ico is no picture
        self.addCleanup(_Site.pages.__setitem__, "/", PAGE)
        _Site.pages["/"] = b"<html><head><title>plain</title></head></html>"
        backend.subscribe(self.base + "/bare.xml")
        self.wait()
        icons = {f["title"]: f["icon"] for f in backend.feeds()}
        self.assertTrue(icons["Local"].endswith(".png"))
        with open(icons["Local"], "rb") as handle:
            self.assertEqual(handle.read(4), b"\x89PNG")
        self.assertEqual(icons["Bare"], "")
        rows = {r["feed"]: r for r in backend.items()}       # the icon comes with each article
        self.assertEqual(rows["Local"]["feedIcon"], icons["Local"])
        self.assertEqual(rows["Bare"]["feedIcon"], "")
        self.assertEqual(backend.open_item(rows["Local"]["iid"])["feedIcon"], icons["Local"])
        # A feed without an icon is not asked again on the next update
        del _Site.hits[:]
        backend.refresh()
        self.wait()
        self.assertEqual(sorted(_Site.hits), ["/bare.xml", "/local.xml"])
        self.assertIn("1 of 2 feeds have an icon. Last problem:", backend.icon_status())
        self.assertIn("favicon.ico: not a PNG", backend.icon_status())
        self.assertEqual(sorted(set(_Site.hits)), ["/bare.xml", "/local.xml"])
        # A lost file is fetched anew at the next start; the feed without one still waits
        _Site.pages["/"] = PAGE
        os.remove(icons["Local"])
        self.assertEqual(backend.find_icons(), 1)
        self.assertEqual(self.wait_for("icons"), ("icons", 1))
        self.assertTrue(os.path.exists(icons["Local"]))
        self.assertEqual(backend.feeds()[0]["icon"], "")
        # Asked for by hand it is tried again: the front page of its site names an icon now
        self.assertEqual(backend.find_icons(again=True), 1)
        self.assertEqual(self.wait_for("icons"), ("icons", 1))
        self.assertEqual(backend.icon_status(), "2 of 2 feeds have an icon.")
        local = [f["fid"] for f in backend.feeds() if f["title"] == "Local"][0]
        backend.remove_feed(local)
        self.assertFalse(os.path.exists(icons["Local"]))

    def test_scrolled_past_and_lead_picture(self):
        backend.subscribe(self.base + "/feed.xml")
        self.wait()
        rows = backend.items()
        self.assertEqual(rows[0]["image"], "http://example.org/a.jpg")
        self.assertEqual(backend.set_read_many([r["iid"] for r in rows]), 0)
        self.assertEqual(backend.open_item(rows[0]["iid"])["lead"], "http://example.org/a.jpg")
        self.assertEqual(backend.open_item(rows[1]["iid"])["lead"], "")

    def test_full_article_from_its_page(self):
        self.addCleanup(_Site.pages.pop, "/story.xml")
        self.addCleanup(_Site.pages.pop, "/story")
        _Site.pages["/story"] = ARTICLE
        _Site.pages["/story.xml"] = (
            '<rss><channel><title>S</title><item><title>Big story</title><link>%s/story</link>'
            '</item><item><title>Gone</title><link>%s/gone</link></item>'
            '<item><title>Empty</title><link>%s/text</link></item></channel></rss>'
            % ((self.base,) * 3)).encode()
        backend.subscribe(self.base + "/story.xml")
        self.wait()
        rows = {r["title"]: r["iid"] for r in backend.items()}
        self.assertFalse(backend.open_item(rows["Big story"])["hasFull"])
        self.assertTrue(backend.open_full(rows["Big story"], 300))
        event = self.wait_for("full")
        self.assertEqual(event[1], rows["Big story"])
        blocks = event[2]["blocks"]
        self.assertIn("The second paragraph", blocks[0]["html"])
        self.assertEqual(blocks[1]["src"], self.base + "/pics/one.jpg")
        self.assertIn("Café owners", blocks[2]["html"])
        self.assertTrue(backend.open_item(rows["Big story"])["hasFull"])
        # Kept: the page is not asked again unless wanted
        del _Site.hits[:]
        backend.open_full(rows["Big story"])
        self.assertIn("The second paragraph", str(self.wait_for("full")[2]["blocks"]))
        self.assertEqual(_Site.hits, [])
        backend.open_full(rows["Big story"], 0, True)
        self.wait_for("full")
        self.assertEqual(_Site.hits, ["/story"])
        # Kept full articles from an older extraction are dropped at the next start
        backend.store.set_version(1)
        path = backend.store.db.execute("PRAGMA database_list").fetchone()[2]
        backend.store.close()
        backend.init(path, os.path.join(self.tmp.name, "cache"))
        self.assertFalse(backend.open_item(rows["Big story"])["hasFull"])
        self.assertEqual(backend.store.version(), backend.FULL_VERSION)
        self.assertFalse(backend.open_item(rows["Big story"])["isVideo"])
        # Failures come back as a message
        backend.open_full(rows["Gone"])
        self.assertIn("404", self.wait_for("full")[2]["error"])
        backend.open_full(rows["Empty"])
        self.assertEqual(self.wait_for("full")[2], {"error": "No article text found on the page"})
        self.assertFalse(backend.open_full(999))

    def test_offline_reading(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
        for path, body in (("/story", ARTICLE), ("/pics/one.jpg", png), ("/text", None),
                           ("/offline.xml", (
                               '<rss><channel><title>O</title><item><title>Big story</title>'
                               '<link>%s/story</link></item><item><title>Gone</title>'
                               '<link>%s/gone</link><description>&lt;p&gt;Short&lt;/p&gt;'
                               '</description></item></channel></rss>'
                               % (self.base, self.base)).encode())):
            if body is not None:
                self.addCleanup(_Site.pages.pop, path, None)
                _Site.pages[path] = body
        backend.subscribe(self.base + "/offline.xml")
        self.wait()
        self.assertTrue(backend.download_offline())
        self.assertIn("2 articles saved for offline reading (1 only with the feed's text)",
                      self.wait())
        rows = {r["title"]: r["iid"] for r in backend.items()}
        article = backend.open_item(rows["Big story"], 300)
        self.assertTrue(article["hasFull"])
        # The full article comes from the phone now, its picture as well
        del _Site.hits[:]
        backend.open_full(rows["Big story"], 300)
        blocks = self.wait_for("full")[2]["blocks"]
        picture = [b["src"] for b in blocks if b["kind"] == "image"][0]
        self.assertTrue(picture.startswith(os.path.join(self.tmp.name, "cache", "pictures")))
        with open(picture, "rb") as handle:
            self.assertEqual(handle.read(), png)
        self.assertEqual(_Site.hits, [])
        # With offline reading on, an update saves the new unread articles too
        backend.set_offline(True)
        self.addCleanup(backend.set_offline, False)
        backend.refresh()
        notices = self.wait()
        # ("Big story" was opened, so it is read: only "Gone" is left)
        self.assertIn("0 new articles · 1 article saved for offline reading "
                      "(1 only with the feed's text)", notices)
        # A big picture is saved whole, then the app is asked to shrink it
        big = b"\xff\xd8\xff" + b"\1" * (backend.SHRINK_BYTES + 10)
        _Site.pages["/big.jpg"] = big
        self.addCleanup(_Site.pages.pop, "/big.jpg", None)
        self.assertTrue(backend._save_picture(self.base + "/big.jpg"))
        path = backend.local_picture(self.base + "/big.jpg")
        self.assertIn(("shrink", path, "jpg"), backend.events)
        self.assertNotIn(("shrink", picture, "png"), backend.events)      # small: left alone
        with open(path + ".small.jpg", "wb") as handle:
            handle.write(b"\xff\xd8\xff small")
        self.assertEqual(backend.shrunk(path, path + ".small.jpg"), len(big) - 9)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), b"\xff\xd8\xff small")
        self.assertFalse(os.path.exists(path + ".small.jpg"))
        # A copy that came out bigger is thrown away; nothing outside the store is touched
        with open(path + ".small.jpg", "wb") as handle:
            handle.write(b"x" * 100)
        self.assertEqual(backend.shrunk(path, path + ".small.jpg"), 0)
        self.assertFalse(os.path.exists(path + ".small.jpg"))
        outside = os.path.join(self.tmp.name, "other.jpg")
        with open(outside, "wb") as handle:
            handle.write(b"x")
        self.assertEqual(backend.shrunk(path, outside), 0)
        self.assertTrue(os.path.exists(outside))
        # Pictures go after a day; one saved again counts from then
        half_day = time.time() - 12 * 3600
        os.utime(picture, (half_day, half_day))
        backend._drop_old_pictures()
        self.assertTrue(os.path.exists(picture))
        two_days = time.time() - 2 * 86400
        os.utime(picture, (two_days, two_days))
        self.assertTrue(backend._save_picture(self.base + "/pics/one.jpg"))
        backend._drop_old_pictures()
        self.assertTrue(os.path.exists(picture))
        os.utime(picture, (two_days, two_days))
        backend._drop_old_pictures()
        self.assertFalse(os.path.exists(picture))
        self.assertEqual(backend.local_picture(self.base + "/pics/one.jpg"),
                         self.base + "/pics/one.jpg")

    def test_missing_opml_file(self):
        backend.import_opml(os.path.join(self.tmp.name, "nope.opml"))
        self.assertIn("Cannot read the file", self.wait()[0])


if __name__ == "__main__":
    unittest.main()
