// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// Ask for an address: a feed, a website that announces its feed, or an OPML file.
import QtQuick 2.6
import Sailfish.Silica 1.0

Dialog {
    id: dialog

    property var app

    canAccept: address.text.trim().length > 3
    onAccepted: app.job("subscribe", [address.text.trim()])

    Component.onCompleted: {
        // Offer an address that was just copied in the browser
        var copied = Clipboard.hasText ? String(Clipboard.text).trim() : ""
        if (/^(https?|feed):\/\/\S+$/i.test(copied) && copied.length < 2000) {
            address.text = copied
        }
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            DialogHeader { acceptText: qsTr("Add") }

            TextField {
                id: address
                width: parent.width
                focus: true
                label: qsTr("Address")
                placeholderText: qsTr("Address of a feed or website")
                inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoAutoUppercase
                                  | Qt.ImhNoPredictiveText
                EnterKey.enabled: dialog.canAccept
                EnterKey.iconSource: "image://theme/icon-m-enter-accept"
                EnterKey.onClicked: dialog.accept()
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.secondaryHighlightColor
                text: qsTr("Enter the address of a feed, or of a website: its feed is looked up. "
                           + "The address of an OPML file imports all the feeds it lists.")
            }
        }
    }
}
