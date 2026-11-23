Name:       harbour-feedpond
Summary:    RSS and Atom feed reader
Version:    0.10.0
Release:    3
License:    GPLv3+
BuildArch:  noarch
Source0:    %{name}-%{version}.tar.bz2

# UI
Requires:   sailfishsilica-qt5 >= 1.1.0
Requires:   mapplauncherd-booster-silica-qt5
# Engine: Python (standard library only), driven through PyOtherSide
Requires:   pyotherside-qml-plugin-python3-qt5
Requires:   python3-base
Requires:   python3-sqlite

%description
Feedpond is a feed reader without an account: it downloads RSS and Atom
feeds straight from their sites and keeps the articles on the phone.
Add a feed by its address or the address of its website, or import your
subscriptions from an OPML file.

%prep
%setup -q -n %{name}-%{version}
# Sources may come from a filesystem without Unix modes (e.g. a Windows drive)
find . -type f -exec chmod 0644 {} +
# ... and with Windows line endings, which break the .desktop file
find . -type f \( -name '*.desktop' -o -name '*.qml' -o -name '*.py' -o -name '*.permission' \) \
    -exec sed -i 's/\r$//' {} +

%build
# Nothing to build: QML UI + Python engine

%install
rm -rf %{buildroot}
install -d %{buildroot}%{_datadir}/%{name}
cp -r qml python %{buildroot}%{_datadir}/%{name}/
find %{buildroot}%{_datadir}/%{name} -name __pycache__ -prune -exec rm -rf {} \;
# Stamp the exact package version into the About page (fail if the marker moved)
sed -i 's/appVersion: "[^"]*"/appVersion: "%{version}-%{release}"/' \
    %{buildroot}%{_datadir}/%{name}/qml/pages/AboutPage.qml
grep -q 'appVersion: "%{version}-%{release}"' %{buildroot}%{_datadir}/%{name}/qml/pages/AboutPage.qml
install -D -m 0644 harbour-feedpond.desktop %{buildroot}%{_datadir}/applications/%{name}.desktop
# Lets the sandboxed app call Speech Note's text-to-speech service (read aloud)
install -D -m 0644 sailjail/FeedpondSpeechNote.permission \
    %{buildroot}%{_sysconfdir}/sailjail/permissions/FeedpondSpeechNote.permission
for size in 86x86 108x108 128x128 172x172; do
    install -D -m 0644 icons/$size/%{name}.png %{buildroot}%{_datadir}/icons/hicolor/$size/apps/%{name}.png
done

%files
%defattr(-,root,root,-)
%{_datadir}/%{name}
%{_datadir}/applications/%{name}.desktop
%config %{_sysconfdir}/sailjail/permissions/FeedpondSpeechNote.permission
%{_datadir}/icons/hicolor/*/apps/%{name}.png

%changelog
* Mon Nov 23 2026 Feedpond contributors - 0.10.0-3
- Article text a little bigger (halfway between the small and the medium font size)

* Fri Nov 20 2026 Feedpond contributors - 0.10.0-2
- Hide read articles: articles scrolled off the top go as soon as the list stops moving

* Fri Nov 20 2026 Feedpond contributors - 0.10.0-1
- Setting "Hide read articles" (same as "Show unread only" in the pull-down menu): read
  articles leave the list on their own - when you come back from one, mark one as read,
  or come back after scrolling past them

* Thu Nov 19 2026 Feedpond contributors - 0.9.0-3
- Pictures saved for offline reading are deleted after one day instead of 30 (at the
  start and after each download); a picture still needed by an unread article is kept

* Thu Nov 19 2026 Feedpond contributors - 0.9.0-2
- Offline reading saves every picture again, then shrinks it to a 720 pixel wide JPEG
  (PNG and WebP too): about 80 % less storage
- Smaller pictures online as well, where a site offers several sizes (responsive pages,
  feed thumbnails): the smallest at least 480 pixels wide instead of a big one

* Thu Nov 19 2026 Feedpond contributors - 0.9.0-1
- Article text is justified (flush left and right); setting "Justified text"
- Offline reading: "Download for offline" in the pull-down menus saves the full text and
  the first pictures of every unread article, so they open without a connection; setting
  "Offline reading" does it after each update. Saved pictures are shown from the phone in
  the articles and lists, and removed after 30 days

* Sat Nov 14 2026 Feedpond contributors - 0.8.0-3
- Read aloud: "Speech Note is not ready" although it was set up - Speech Note refuses to
  speak while it is still starting ("busy"). Feedpond now waits until it is idle (up to
  30 s) and tries again shortly if it still refuses; it says when Speech Note has no
  text-to-speech voice, and otherwise shows Speech Note's state and voice count

* Sat Nov 14 2026 Feedpond contributors - 0.8.0-2
- Read aloud: "Speech Note cannot be reached" - the app sandbox lets an app call only the
  D-Bus services its permissions name. New sailjail permission FeedpondSpeechNote (installed
  to /etc/sailjail/permissions) allows exactly Speech Note's org.mkiol.Speech
- The error shows the full D-Bus error name and message

* Sat Nov 14 2026 Feedpond contributors - 0.8.0-1
- Read aloud (optional, needs Speech Note from OpenRepos with a voice): speaker button at
  the top of each article and "Read aloud" in its pull-down menu; a bar at the bottom shows
  the sentence being read, with pause/resume and stop. Reads the title and the text shown
  (feed text or full article) with Speech Note's default voice; stops when the article is
  left. Setting "Read aloud" to hide the button

* Thu Nov 12 2026 Feedpond contributors - 0.7.0-1
- YouTube and Vimeo videos play in the app, with sound, on a page of their own (the site's
  player in a web view; turn the phone for full screen). Press and hold a video to open it
  outside the app. Sailjail permission WebView
- Share: button at the top of each article, and "Share" in the article's pull-down menu and
  in the press-and-hold menu of the article lists (the system share menu; the link is
  copied where there is none)

* Thu Nov 12 2026 Feedpond contributors - 0.6.0-1
- Setting "Always open the full article": articles load from their web page as soon as they
  are opened (not for YouTube/Vimeo videos); the feed's text stays in the pull-down menu
- Full articles leave out shop buttons ("Zum Angebot") and the "see also" label of the link
  lists they already left out (winfuture.de)
- Full articles kept from earlier versions are read again with the better extraction

* Thu Nov 12 2026 Feedpond contributors - 0.5.0-2
- Links in articles were still Qt's dark blue: a rich-text label ignores its link colour.
  Each link now carries the text colour (underlined) itself

* Tue Nov 10 2026 Feedpond contributors - 0.5.0-1
- Only the 25 newest articles of each feed are kept; older ones are removed at the start and
  after each update, and do not come back while the feed still lists them
- Reading time on top of each article, for the feed's text or the full article

* Tue Nov 10 2026 Feedpond contributors - 0.4.0-2
- Full articles from pages that write their text without paragraphs (winfuture.de) are found
  whole; author boxes and "read also" link lists are left out; pages that show their text
  only after a consent check fall back to the text they carry for search engines
- Video previews: a video file without a picture shows a frame of itself, Vimeo videos get
  their picture, YouTube articles get one in the article lists, and the link shown with
  videos switched off has the picture too

* Tue Nov 10 2026 Feedpond contributors - 0.4.0-1
- Pictures in articles are shown as real pictures between the paragraphs (they were left to
  the text renderer before, which often showed nothing); tap one to open it or its link
- Videos in articles and full articles: video files (and videos a feed encloses) play in
  the article, tap to pause or on the time bar to jump; YouTube and Vimeo show their
  picture and open in the browser or a video app. Setting "Videos in articles"
- Links in article text have the text colour, underlined, instead of the ambience colour
- Sailjail permission Audio, for the sound of videos

* Tue Nov 10 2026 Feedpond contributors - 0.3.0-1
- "Open full article" loads the article's web page and shows its text in the app, without
  menus, ads and comments; it is kept, so it opens at once the next time. The pull-down menu
  switches between the full article and the feed's text, or loads it again
- Setting "Full articles in the app": off opens the page in the browser as before
- Pictures of lazy-loading pages (data-src, srcset) are found

* Mon Nov 09 2026 Feedpond contributors - 0.2.0-5
- Swipe navigation: swipe left from the combined list for the feeds, and left again for the
  feed opened last; swipe right to go back the same way

* Mon Nov 09 2026 Feedpond contributors - 0.2.0-4
- Combined list: a feed without an icon shows its first letter in a circle, as in the list
  of feeds, instead of nothing
- Icons are looked for in more places (the website's front page and the feed's own host);
  feeds left without one are tried again once after this update

* Mon Nov 09 2026 Feedpond contributors - 0.2.0-3
- Feed icons are fetched right after the start for all feeds that have none, without waiting
  for an update; a failed download (no connection) is tried again instead of after a week
- About page: how many feeds have an icon, the last problem, and "Look for icons again"

* Mon Nov 09 2026 Feedpond contributors - 0.2.0-2
- The list with the articles of all feeds is the home page now, so going back always ends
  there; the feeds are opened from its pull-down menu
- The feed's icon is also shown next to the feed name in the combined list, in the header
  of a feed's own list and in the header of an article

* Mon Nov 09 2026 Feedpond contributors - 0.2.0-1
- The app opens on one list with the articles of all feeds; swipe back for the feeds
- Feed icons: the website's icon is downloaded once and shown in the list of feeds
- Article pictures: a thumbnail next to each article, and the article's picture on top of
  its text when the text has none
- Articles scrolled past are marked as read
- Settings page to switch each of these off

* Mon Nov 09 2026 Feedpond contributors - 0.1.0-2
- Adding a feed and importing OPML did nothing: the first page never got its link to the
  application window, so every action was dropped silently

* Mon Nov 09 2026 Feedpond contributors - 0.1.0-1
- Initial release: RSS and Atom feeds, feed discovery from a website address, OPML import
  (file or address) and export, folders from OPML, unread tracking, article view
