// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// The articles of one feed (feedId) or of all feeds (feedId 0), newest first.
import QtQuick 2.6
import Sailfish.Silica 1.0

Page {
    id: page

    property var app
    property int feedId: 0
    property string feedTitle: ""
    property string feedIcon: ""      // icon file of the one feed shown
    property bool home: false         // the app's first page: leads on to the feeds

    readonly property int pageSize: 60
    property bool loading: false
    property bool more: true          // the last page was full, so there may be another
    property int generation: 0        // answers to an outdated request are dropped
    property int scrolledPast: -1     // rows up to this one were handled by markScrolledPast

    function reload() {
        generation += 1
        itemModel.clear()
        scrolledPast = -1
        loading = false
        more = true
        loadMore()
    }

    function loadMore() {
        if (loading || !more || !app.ready) return
        loading = true
        var asked = generation
        var last = itemModel.count > 0 ? itemModel.get(itemModel.count - 1) : null
        app.call("items", [feedId, app.unreadOnly, pageSize,
                           last ? last.published : 0, last ? last.iid : 0], function (rows) {
            if (asked !== page.generation) return
            for (var i = 0; i < rows.length; ++i) itemModel.append(rows[i])
            page.more = rows.length === page.pageSize
            page.loading = false
        })
    }

    function setRead(index, read) {
        var row = itemModel.get(index)
        if ((row.read !== 0) === read) return
        itemModel.setProperty(index, "read", read ? 1 : 0)
        app.call("set_read", [row.iid, read], function (unread) { page.app.unread = unread })
        if (read && app.unreadOnly) dropRead()
    }

    // Unread only: read articles leave the list (back from an article, marked by hand or
    // scrolled past). The row at the top of the screen stays where it is.
    function dropRead() {
        if (!app.unreadOnly || itemModel.count === 0) return
        var top = list.indexAt(list.width / 2, list.contentY + 1)
        var topItem = list.itemAt(list.width / 2, list.contentY + 1)
        var keep = -1, offset = 0
        for (var i = Math.max(top, 0); i < itemModel.count; ++i) {
            if (itemModel.get(i).read === 0) { keep = itemModel.get(i).iid; break }
        }
        // The half-visible top row stays exactly where it is
        if (top >= 0 && topItem && itemModel.get(top).iid === keep) offset = list.contentY - topItem.y
        for (var j = itemModel.count - 1; j >= 0; --j) {
            if (itemModel.get(j).read !== 0) itemModel.remove(j)
        }
        scrolledPast = -1
        if (keep < 0) return
        for (var k = 0; k < itemModel.count; ++k) {
            if (itemModel.get(k).iid === keep) {
                scrolledPast = k - 1
                if (top > 0) {
                    list.positionViewAtIndex(k, ListView.Beginning)
                    list.contentY += offset
                }
                break
            }
        }
        if (itemModel.count < pageSize / 2) loadMore()
    }

    // Everything above the first visible row has been scrolled past: mark it read.
    // Each row is handled once, so an article set back to unread by hand stays unread.
    function markScrolledPast() {
        if (!app.markOnScroll) return
        var first = list.indexAt(list.width / 2, list.contentY + 1)
        if (first <= scrolledPast + 1) return
        var ids = []
        for (var i = scrolledPast + 1; i < first; ++i) {
            var row = itemModel.get(i)
            if (row.read === 0) {
                ids.push(row.iid)
                itemModel.setProperty(i, "read", 1)
            }
        }
        scrolledPast = first - 1
        if (ids.length > 0) {
            app.call("set_read_many", [ids, true], function (unread) { page.app.unread = unread })
        }
    }

    // The page a swipe forward leads to, if one is attached
    function pageAhead() {
        try {
            return pageStack.nextPage(page) || null
        } catch (error) {
            return null
        }
    }

    // Home keeps the list of feeds attached, so a swipe forward opens it and a swipe back
    // returns here. Pushing another page (an article) drops it; it is attached again on return.
    function attachFeeds() {
        if (home && status === PageStatus.Active && !pageAhead()) {
            try {
                pageStack.pushAttached(Qt.resolvedUrl("FeedsPage.qml"), { app: app })
            } catch (error) {
                console.log("Feeds page not attached:", error)   // the menu entry still works
            }
        }
    }

    function openFeeds() {
        if (pageAhead()) {
            pageStack.navigateForward()
        } else {
            pageStack.push(Qt.resolvedUrl("FeedsPage.qml"), { app: app })
        }
    }

    Component.onCompleted: reload()
    onStatusChanged: {
        attachFeeds()
        if (status === PageStatus.Active) dropRead()      // back from an article
    }

    Connections {
        target: app
        // Not in the middle of an update (the list would jump); one more follows its end
        onRevisionChanged: if (!app.busy) page.reload()
        onUnreadOnlyChanged: page.reload()
        onReadyChanged: page.reload()
    }

    ListModel { id: itemModel }

    Timer {
        id: scrollTimer
        interval: 250
        onTriggered: page.markScrolledPast()
    }

    SilicaListView {
        id: list
        anchors.fill: parent
        model: itemModel

        onAtYEndChanged: if (atYEnd) page.loadMore()
        // Only the user's own scrolling counts, not the list settling after a reload
        onContentYChanged: if (moving && app.markOnScroll) scrollTimer.start()
        // Not while the finger moves the list: rows vanishing under it would jump
        onMovementEnded: {
            scrollTimer.stop()
            page.markScrolledPast()
            page.dropRead()
        }

        PullDownMenu {
            busy: app.busy
            MenuItem {
                text: qsTr("Feeds")
                visible: page.home
                onClicked: page.openFeeds()
            }
            MenuItem {
                text: app.unreadOnly ? qsTr("Show all articles") : qsTr("Show unread only")
                onClicked: app.unreadOnly = !app.unreadOnly
            }
            MenuItem {
                text: qsTr("Mark all as read")
                onClicked: app.call("mark_all_read", [page.feedId])
            }
            MenuItem {
                // Full text and pictures of every unread article, to read without a connection
                text: qsTr("Download for offline")
                visible: page.home
                enabled: !app.busy
                onClicked: app.job("download_offline", [])
            }
            MenuItem {
                text: page.feedId ? qsTr("Update") : qsTr("Update all")
                enabled: !app.busy
                onClicked: app.job("refresh", [page.feedId])
            }
        }

        header: FeedHeader {
            width: list.width
            icon: page.feedIcon
            title: page.feedTitle
            description: app.busy ? app.busyText
                       : app.notice !== "" ? app.notice
                       : app.unreadOnly ? qsTr("Unread only") : ""
        }

        delegate: ListItem {
            id: articleItem
            contentHeight: Math.max(body.height, picture.width > 0 ? picture.height : 0)
                           + 2 * Theme.paddingMedium

            onClicked: {
                itemModel.setProperty(index, "read", 1)     // the engine marks it on opening
                pageStack.push(Qt.resolvedUrl("ArticlePage.qml"),
                               { app: page.app, itemId: model.iid })
            }

            Image {
                id: picture
                readonly property bool wanted: page.app.listImages && model.image !== ""
                anchors { right: parent.right; rightMargin: Theme.horizontalPageMargin }
                y: Theme.paddingMedium
                width: wanted && status !== Image.Error ? Theme.itemSizeLarge : 0
                height: Theme.itemSizeLarge
                source: wanted ? model.image : ""
                sourceSize.width: 2 * Theme.itemSizeLarge
                fillMode: Image.PreserveAspectCrop
                clip: true
                asynchronous: true
                opacity: status === Image.Ready ? (model.read === 0 ? 1.0 : 0.6) : 0.0
                Behavior on opacity { FadeAnimation {} }
            }

            Column {
                id: body
                x: Theme.horizontalPageMargin
                y: Theme.paddingMedium
                width: parent.width - 2 * x
                       - (picture.width > 0 ? picture.width + Theme.paddingMedium : 0)

                Label {
                    width: parent.width
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    truncationMode: TruncationMode.Elide
                    font.bold: model.read === 0
                    color: articleItem.highlighted ? Theme.highlightColor
                         : model.read === 0 ? Theme.primaryColor : Theme.secondaryColor
                    text: model.title
                }
                Label {
                    width: parent.width
                    visible: model.summary !== "" && model.summary !== model.title
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    truncationMode: TruncationMode.Elide
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: articleItem.highlighted ? Theme.secondaryHighlightColor
                                                   : Theme.secondaryColor
                    opacity: model.read === 0 ? 1.0 : 0.7
                    text: model.summary
                }
                Row {
                    width: parent.width
                    spacing: Theme.paddingSmall

                    FeedIcon {
                        id: rowIcon
                        anchors.verticalCenter: parent.verticalCenter
                        visible: page.feedId === 0
                        icon: model.feedIcon
                        title: model.feed          // no icon: the feed's first letter
                        size: Theme.iconSizeExtraSmall
                    }
                    Label {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - (rowIcon.visible ? rowIcon.width + parent.spacing : 0)
                        truncationMode: TruncationMode.Fade
                        font.pixelSize: Theme.fontSizeExtraSmall
                        color: Theme.secondaryHighlightColor
                        text: (page.feedId ? "" : model.feed + "  ·  ")
                              + Format.formatDate(new Date(model.published * 1000),
                                                  Formatter.TimepointRelative)
                    }
                }
            }

            menu: ContextMenu {
                MenuItem {
                    text: model.read === 0 ? qsTr("Mark as read") : qsTr("Mark as unread")
                    onClicked: page.setRead(index, model.read === 0)
                }
                MenuItem {
                    text: qsTr("Open in browser")
                    visible: model.link !== ""
                    onClicked: {
                        page.setRead(index, true)
                        Qt.openUrlExternally(model.link)
                    }
                }
                MenuItem {
                    text: qsTr("Share")
                    visible: model.link !== ""
                    onClicked: page.app.share(model.title, model.link)
                }
            }
        }

        ViewPlaceholder {
            enabled: app.ready && itemModel.count === 0 && !page.loading && !app.busy
            text: app.unreadOnly ? qsTr("Nothing unread") : qsTr("No articles")
            hintText: app.unreadOnly ? qsTr("Pull down to show all articles")
                    : page.home ? qsTr("Swipe left for the feeds, to add or import some")
                                : qsTr("Pull down to update")
        }

        VerticalScrollDecorator {}
    }
}
