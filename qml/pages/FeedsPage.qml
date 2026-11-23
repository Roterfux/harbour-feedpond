// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// The subscriptions, grouped by folder, with their unread counts.
import QtQuick 2.6
import Sailfish.Silica 1.0
import Sailfish.Pickers 1.0

Page {
    id: page

    property var app                  // the ApplicationWindow (engine + shared state)

    function reload() {
        if (!app.ready) return
        app.call("feeds", [], function (rows) {
            var same = rows.length === feedModel.count
            for (var i = 0; same && i < rows.length; ++i) {
                same = feedModel.get(i).fid === rows[i].fid
            }
            if (same) {               // keep the scroll position: update in place
                for (i = 0; i < rows.length; ++i) feedModel.set(i, rows[i])
            } else {
                feedModel.clear()
                for (i = 0; i < rows.length; ++i) feedModel.append(rows[i])
            }
        })
    }

    // The feed's list is attached, not pushed: after a swipe back to this page, a swipe
    // forward returns to the same feed.
    function openArticles(feedId, title, icon) {
        var properties = { app: app, feedId: feedId, feedTitle: title, feedIcon: icon }
        var ahead = null
        try {
            ahead = pageStack.nextPage(page) || null
        } catch (error) {
            ahead = null
        }
        if (ahead && ahead.feedId === feedId) {          // already attached: just go there
            pageStack.navigateForward()
            return
        }
        try {
            pageStack.pushAttached(Qt.resolvedUrl("ItemsPage.qml"), properties)
            pageStack.navigateForward()
        } catch (error) {
            pageStack.push(Qt.resolvedUrl("ItemsPage.qml"), properties)
        }
    }

    onStatusChanged: if (status === PageStatus.Active) reload()

    Connections {
        target: app
        onRevisionChanged: page.reload()
    }

    ListModel { id: feedModel }

    Component {
        id: opmlPicker
        FilePickerPage {
            title: qsTr("Import OPML file")
            nameFilters: ["*.opml", "*.xml"]
            onSelectedContentPropertiesChanged: {
                if (selectedContentProperties && selectedContentProperties.filePath) {
                    page.app.job("import_opml", [String(selectedContentProperties.filePath)])
                }
            }
        }
    }

    SilicaListView {
        id: list
        anchors.fill: parent
        model: feedModel

        PullDownMenu {
            busy: app.busy
            MenuItem {
                text: qsTr("About")
                onClicked: pageStack.push(Qt.resolvedUrl("AboutPage.qml"), { app: app })
            }
            MenuItem {
                text: qsTr("Settings")
                onClicked: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"), { app: app })
            }
            MenuItem {
                text: qsTr("Export OPML")
                visible: feedModel.count > 0
                onClicked: app.call("export_opml", [])
            }
            MenuItem {
                text: qsTr("Import OPML file")
                enabled: app.ready && !app.busy
                onClicked: pageStack.push(opmlPicker)
            }
            MenuItem {
                text: qsTr("Add feed")
                enabled: app.ready && !app.busy
                onClicked: pageStack.push(Qt.resolvedUrl("AddFeedDialog.qml"), { app: app })
            }
            MenuItem {
                text: qsTr("Download for offline")
                visible: feedModel.count > 0
                enabled: !app.busy
                onClicked: app.job("download_offline", [])
            }
            MenuItem {
                text: qsTr("Update all")
                visible: feedModel.count > 0
                enabled: !app.busy
                onClicked: app.job("refresh", [0])
            }
        }

        header: Column {
            width: list.width

            PageHeader {
                title: qsTr("Feedpond")
                description: app.busy ? app.busyText : ""
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                height: visible ? implicitHeight + Theme.paddingMedium : 0
                visible: app.notice !== "" && !app.busy
                wrapMode: Text.Wrap
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.secondaryHighlightColor
                text: app.notice
            }

            BackgroundItem {
                width: parent.width
                height: Theme.itemSizeSmall
                visible: feedModel.count > 0
                // The combined list is the page below this one
                onClicked: pageStack.navigateBack()

                Label {
                    anchors { left: parent.left; leftMargin: Theme.horizontalPageMargin
                              right: allCount.left; rightMargin: Theme.paddingMedium
                              verticalCenter: parent.verticalCenter }
                    truncationMode: TruncationMode.Fade
                    color: parent.highlighted ? Theme.highlightColor : Theme.primaryColor
                    text: qsTr("All articles")
                }
                Label {
                    id: allCount
                    anchors { right: parent.right; rightMargin: Theme.horizontalPageMargin
                              verticalCenter: parent.verticalCenter }
                    color: Theme.highlightColor
                    text: app.unread > 0 ? app.unread : ""
                }
            }
        }

        section.property: "tag"
        section.delegate: SectionHeader {
            text: section
            visible: section !== ""
            height: visible ? Theme.itemSizeExtraSmall : 0
        }

        delegate: ListItem {
            id: feedItem
            contentHeight: model.error !== "" ? Theme.itemSizeMedium : Theme.itemSizeSmall
            onClicked: page.openArticles(model.fid, model.title, model.icon)

            function remove() {
                var id = model.fid
                remorseAction(qsTr("Removing"), function () { page.app.call("remove_feed", [id]) })
            }

            FeedIcon {
                id: iconBox
                anchors { left: parent.left; leftMargin: Theme.horizontalPageMargin
                          verticalCenter: parent.verticalCenter }
                icon: model.icon
                title: model.title
            }

            Column {
                anchors { left: iconBox.right; leftMargin: Theme.paddingMedium
                          right: unreadCount.left; rightMargin: Theme.paddingMedium
                          verticalCenter: parent.verticalCenter }
                Label {
                    width: parent.width
                    truncationMode: TruncationMode.Fade
                    color: feedItem.highlighted ? Theme.highlightColor
                         : model.unread > 0 ? Theme.primaryColor : Theme.secondaryColor
                    text: model.title
                }
                Label {
                    width: parent.width
                    visible: model.error !== ""
                    truncationMode: TruncationMode.Fade
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: Theme.errorColor
                    text: model.error
                }
            }
            Label {
                id: unreadCount
                anchors { right: parent.right; rightMargin: Theme.horizontalPageMargin
                          verticalCenter: parent.verticalCenter }
                color: Theme.highlightColor
                text: model.unread > 0 ? model.unread : ""
            }

            menu: ContextMenu {
                MenuItem {
                    text: qsTr("Update")
                    enabled: !app.busy
                    onClicked: app.job("refresh", [model.fid])
                }
                MenuItem {
                    text: qsTr("Mark all as read")
                    onClicked: app.call("mark_all_read", [model.fid])
                }
                MenuItem {
                    text: qsTr("Remove")
                    onClicked: feedItem.remove()
                }
            }
        }

        ViewPlaceholder {
            enabled: app.ready && !app.busy && feedModel.count === 0
            text: qsTr("No feeds yet")
            hintText: qsTr("Pull down to add a feed or to import an OPML file")
        }

        VerticalScrollDecorator {}
    }
}
