// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick 2.6
import Sailfish.Silica 1.0

Page {
    id: page

    property var app
    property string iconStatus: ""
    property bool searching: false

    // The RPM build stamps the exact package version in here (see rpm/*.spec)
    readonly property string appVersion: "development"

    function showIconStatus() {
        if (app) app.call("icon_status", [], function (text) { page.iconStatus = text })
    }

    Component.onCompleted: showIconStatus()

    Connections {
        target: page.app
        onIconRunsChanged: { page.searching = false; page.showIconStatus() }
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height + Theme.paddingLarge

        Column {
            id: column
            width: parent.width
            spacing: Theme.paddingMedium

            PageHeader { title: qsTr("About") }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                color: Theme.highlightColor
                font.pixelSize: Theme.fontSizeLarge
                text: "Feedpond " + appVersion
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                color: Theme.primaryColor
                font.pixelSize: Theme.fontSizeSmall
                text: qsTr("A feed reader without an account. Feeds are downloaded straight from "
                           + "their sites, and the articles are kept on this phone only.")
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
                text: qsTr("OPML files to import are looked for in Documents and Downloads. "
                           + "The export is saved to Documents as feedpond-feeds.opml.")
            }

            SectionHeader { text: qsTr("Feed icons") }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
                text: page.searching ? qsTr("Looking for icons…") : page.iconStatus
            }

            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                text: qsTr("Look for icons again")
                enabled: !page.searching
                onClicked: page.app.call("find_icons", [true], function (count) {
                    page.searching = count > 0
                    if (!count) page.showIconStatus()
                })
            }

            Item { width: 1; height: Theme.paddingLarge }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeExtraSmall
                text: qsTr("Free software under the GNU General Public License, version 3 or later. "
                           + "Built with Sailfish Silica, PyOtherSide and Python.")
            }
        }

        VerticalScrollDecorator {}
    }
}
