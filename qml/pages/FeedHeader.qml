// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// A page header with the feed's icon to the right of the title (when there is one).
import QtQuick 2.6
import Sailfish.Silica 1.0

Item {
    id: root

    property alias title: header.title
    property alias description: header.description
    property string icon: ""

    width: parent ? parent.width : Screen.width
    height: header.height

    PageHeader {
        id: header
        rightMargin: Theme.horizontalPageMargin
                     + (feedIcon.width > 0 ? feedIcon.width + Theme.paddingMedium : 0)
    }

    FeedIcon {
        id: feedIcon
        icon: root.icon
        letter: false
        visible: width > 0
        anchors { right: parent.right; rightMargin: Theme.horizontalPageMargin }
        // Level with the title, which keeps its place when a description is shown below it
        y: Math.round((Math.min(header.height, Theme.itemSizeLarge) - height) / 2)
    }
}
