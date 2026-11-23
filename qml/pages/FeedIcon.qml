// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// A feed's icon from the cache. Without one (or with one Qt cannot show) it is the
// feed's first letter in a circle, or nothing at all (width 0) when letter is false.
import QtQuick 2.6
import Sailfish.Silica 1.0

Item {
    id: root

    property string icon: ""          // file path, "" = none
    property string title: ""
    property bool letter: true
    property real size: Theme.iconSizeSmall
    readonly property bool shown: picture.status === Image.Ready || letter

    width: shown ? size : 0
    height: size

    Image {
        id: picture
        anchors.fill: parent
        source: root.icon !== "" ? "file://" + root.icon : ""
        sourceSize { width: root.size; height: root.size }
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        visible: status === Image.Ready
    }

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        visible: root.letter && picture.status !== Image.Ready
        color: Theme.rgba(Theme.highlightBackgroundColor, 0.3)
        Label {
            anchors.centerIn: parent
            font.pixelSize: Math.round(root.size * 0.6)
            color: Theme.highlightColor
            text: root.title.charAt(0).toUpperCase()
        }
    }
}
