// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick 2.6
import Sailfish.Silica 1.0
import Nemo.Configuration 1.0
import io.thp.pyotherside 1.3
import "pages"

ApplicationWindow {
    // Not "app": the pages have a property of that name, and inside the initialPage
    // component "app: app" would bind the page's property to itself (undefined).
    id: appWindow

    property bool ready: false        // the engine is loaded and the database open
    property bool busy: false         // a download job runs
    property int busyDone: 0
    property int busyTotal: 0         // 0 = no count yet
    property int unread: 0
    property int revision: 0          // goes up whenever stored data changed: pages reload
    property string notice: ""        // the last result or error, shown on the feeds page
    property int iconRuns: 0          // goes up when a search for feed icons has ended
    property alias unreadOnly: cfg.unreadOnly
    property alias markOnScroll: cfg.markOnScroll     // articles scrolled past become read
    property alias listImages: cfg.listImages         // pictures in the article lists
    property alias fullInApp: cfg.fullInApp           // "Open full article" reads it here
    property alias alwaysFull: cfg.alwaysFull         // articles open as full article
    property alias videos: cfg.videos                 // videos shown and played in articles
    property alias readAloud: cfg.readAloud           // read-aloud button (needs Speech Note)
    property alias justify: cfg.justify               // article text flush left and right
    property alias offline: cfg.offline               // after updates, save unread for offline
    // Reading aloud through Speech Note; null where Nemo.DBus is missing
    readonly property var speaker: speakerLoader.item
    // Links in article text: the text's own colour (readable on every ambience), underlined.
    // A rich-text Label ignores its linkColor (Qt draws links in its default dark blue), so
    // each link gets the colour as an inline style, which beats Qt's own rule for links.
    readonly property color linkColor: Theme.primaryColor
    readonly property string linkStyle: 'style="color: ' + hexColor(linkColor)
                                        + '; text-decoration: underline" '

    // A YouTube or Vimeo video block: played in the app's web view, or in the browser when
    // this phone has none for apps (Sailfish.WebView missing)
    function playEmbed(block) {
        var page = Qt.createComponent(Qt.resolvedUrl("pages/WebVideoPage.qml"))
        if (page.status === Component.Ready && block.play) {
            pageStack.push(page, { app: appWindow, url: block.play, link: block.url })
        } else {
            if (page.status === Component.Error) console.log(page.errorString())
            Qt.openUrlExternally(block.url)
        }
    }

    // Share an article's address through the system's share menu; without one (older
    // Sailfish OS) the address is copied
    property var shareAction: null
    function share(title, link) {
        if (!link) return
        if (shareAction === null) {
            try {
                shareAction = Qt.createQmlObject(
                    'import Sailfish.Share 1.0; ShareAction { mimeType: "text/x-url" }',
                    appWindow, "share")
            } catch (error) {
                console.log("No share menu:", error)
                shareAction = false
            }
        }
        if (shareAction) {
            shareAction.title = qsTr("Share link")
            shareAction.resources = [{ "type": "text/x-url", "linkTitle": title, "status": link }]
            shareAction.trigger()
        } else {
            Clipboard.text = link
            notice = qsTr("Link copied")
        }
    }

    function styleLinks(markup) {
        return markup.replace(/<a /g, "<a " + linkStyle)
    }

    function hexColor(c) {
        function two(v) {
            var s = Math.round(v * 255).toString(16)
            return s.length < 2 ? "0" + s : s
        }
        return "#" + two(c.r) + two(c.g) + two(c.b)
    }

    // The engine's answer to open_full: {content} or {error}
    signal fullArticle(int itemId, var result)

    property string busyKind: ""      // "offline": saving articles, else updating
    readonly property string busyText: !busy ? ""
        : busyTotal > 0 && busyKind === "offline"
          ? qsTr("Saving for offline %1 of %2").arg(busyDone).arg(busyTotal)
        : busyTotal > 0 ? qsTr("Updating %1 of %2").arg(busyDone).arg(busyTotal)
                        : qsTr("Loading")

    // Call a function of python/backend.py; the callback gets its result
    function call(name, args, callback) {
        py.call("backend." + name, args || [], callback || function () {})
    }

    // For the calls that start a background job (they answer false while one runs)
    function job(name, args) {
        notice = ""
        call(name, args, function (started) {
            if (!started) appWindow.notice = qsTr("Still busy, try again in a moment")
        })
    }

    ConfigurationGroup {
        id: cfg
        path: "/apps/harbour-feedpond"
        property bool unreadOnly: false
        property bool markOnScroll: true
        property bool listImages: true
        property bool fullInApp: true
        property bool alwaysFull: false
        property bool videos: true
        property bool readAloud: true
        property bool justify: true
        property bool offline: false
    }
    // The engine reads this one itself after its updates
    onOfflineChanged: if (ready) call("set_offline", [offline])

    Loader {
        id: speakerLoader
        source: "pages/ReadAloud.qml"
    }

    Shrinker {
        id: shrinker
        app: appWindow
    }

    Python {
        id: py
        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl("../python"))
            setHandler("busy", function (on, done, total, kind) {
                appWindow.busy = on
                appWindow.busyDone = done
                appWindow.busyTotal = total
                appWindow.busyKind = kind || ""
            })
            setHandler("changed", function (unread) {
                appWindow.unread = unread
                appWindow.revision += 1
            })
            setHandler("notice", function (text) { appWindow.notice = text })
            setHandler("icons", function (found) { appWindow.iconRuns += 1 })
            setHandler("shrink", function (path, kind) { shrinker.add(path, kind) })
            setHandler("full", function (itemId, result) {
                appWindow.fullArticle(itemId, result)
            })
            importModule("backend", function () {
                py.call("backend.init", [], function (unread) {
                    appWindow.unread = unread
                    py.call("backend.set_offline", [appWindow.offline], function () {})
                    appWindow.ready = true
                    appWindow.revision += 1
                    // Feeds still without an icon get theirs now, quietly
                    py.call("backend.find_icons", [], function () {})
                })
            })
        }
        onError: {
            appWindow.busy = false
            appWindow.notice = qsTr("Error: %1").arg(traceback)
        }
    }

    allowedOrientations: defaultAllowedOrientations
    // Home is the one list with the articles of all feeds; the feeds are a page above it
    initialPage: Component {
        ItemsPage { app: appWindow; home: true; feedTitle: qsTr("All articles") }
    }

    cover: Component {
        CoverBackground {
            Column {
                anchors { left: parent.left; right: parent.right; margins: Theme.paddingLarge
                          verticalCenter: parent.verticalCenter
                          verticalCenterOffset: -Theme.paddingLarge }
                Label {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: Theme.fontSizeHuge
                    color: Theme.highlightColor
                    text: appWindow.unread
                }
                Label {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    color: Theme.secondaryHighlightColor
                    text: appWindow.busy ? appWindow.busyText : qsTr("unread")
                }
            }
            CoverActionList {
                enabled: appWindow.ready && !appWindow.busy
                CoverAction {
                    iconSource: "image://theme/icon-cover-refresh"
                    onTriggered: appWindow.job("refresh", [0])
                }
            }
        }
    }
}
