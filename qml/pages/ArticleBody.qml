// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// An article's text, pictures and videos, as the engine cut them into blocks
// (see article_blocks in python/feedparse.py).
import QtQuick 2.6
import Sailfish.Silica 1.0

Column {
    id: body

    property var app
    property var blocks: []
    property bool active: true        // the page is on screen: a video may play

    width: parent ? parent.width : 0
    spacing: Theme.paddingMedium

    Repeater {
        model: body.blocks
        delegate: Loader {
            width: body.width
            property var block: modelData
            sourceComponent: modelData.kind === "text" ? textBlock
                           : modelData.kind === "image" ? imageBlock
                           : body.app.videos ? videoBlock : videoLink
        }
    }

    Component {
        id: textBlock
        Item {
            height: label.height
            Label {
                id: label
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                textFormat: Text.RichText
                // Flush left and right (checked: rich text honours the label's alignment)
                horizontalAlignment: body.app.justify ? Text.AlignJustify : Text.AlignLeft
                font.pixelSize: Math.round((Theme.fontSizeSmall + Theme.fontSizeMedium) / 2)
                color: Theme.primaryColor
                linkColor: body.app.linkColor
                text: parent.parent ? body.app.styleLinks(parent.parent.block.html) : ""
                onLinkActivated: Qt.openUrlExternally(link)
            }
        }
    }

    Component {
        id: imageBlock
        BackgroundItem {
            id: pictureItem
            readonly property var block: parent ? parent.block : ({})
            readonly property real full: width - 2 * Theme.horizontalPageMargin
            // Small pictures keep their size, big ones fill the text width
            readonly property real wanted: block.width > 0 && block.width * Theme.pixelRatio < full
                                           ? block.width * Theme.pixelRatio : full
            height: picture.status === Image.Error ? 0
                  : picture.status === Image.Ready ? picture.height
                  : block.width > 0 && block.height > 0
                    ? Math.round(wanted * block.height / block.width) : Theme.itemSizeHuge
            enabled: picture.status === Image.Ready
            onClicked: Qt.openUrlExternally(block.link || block.src)

            Rectangle {
                anchors.fill: parent
                anchors { leftMargin: Theme.horizontalPageMargin; rightMargin: Theme.horizontalPageMargin }
                visible: picture.status === Image.Loading
                color: Theme.rgba(Theme.highlightBackgroundColor, 0.1)
            }

            Image {
                id: picture
                x: Math.round((parent.width - width) / 2)
                width: pictureItem.wanted
                height: implicitWidth > 0 ? Math.round(width * implicitHeight / implicitWidth) : 0
                source: pictureItem.block.src || ""
                sourceSize.width: Math.round(width)
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                opacity: status === Image.Ready ? 1.0 : 0.0
                Behavior on opacity { FadeAnimation {} }
            }
        }
    }

    Component {
        id: videoBlock
        Item {
            id: videoItem
            readonly property var block: parent ? parent.block : ({})
            readonly property bool external: block.kind === "embed"
            property bool playing: false
            property string foundPoster: ""       // looked up (Vimeo)
            property bool noPlayer: false         // the phone cannot play video in the app
            readonly property string poster: block.poster || foundPoster
            // A video file without a picture shows its own first frame instead
            readonly property bool framePreview: !external && !poster && !noPlayer

            height: frame.height + caption.height + Theme.paddingSmall

            Component.onCompleted: {
                if (block.site === "Vimeo" && !block.poster) {
                    var request = new XMLHttpRequest()
                    request.onreadystatechange = function () {
                        if (request.readyState !== XMLHttpRequest.DONE || request.status !== 200)
                            return
                        try {
                            videoItem.foundPoster = JSON.parse(request.responseText).thumbnail_url || ""
                        } catch (error) {
                            console.log("No Vimeo picture:", error)
                        }
                    }
                    request.open("GET", "https://vimeo.com/api/oembed.json?width=640&url="
                                 + encodeURIComponent(block.url))
                    request.send()
                }
            }

            Rectangle {
                id: frame
                width: parent.width
                height: Math.round(width * 9 / 16)
                color: "black"
            }
            Image {
                anchors.fill: frame
                visible: !videoItem.playing
                source: videoItem.poster
                sourceSize.width: frame.width
                fillMode: Image.PreserveAspectCrop
                clip: true
                asynchronous: true
            }
            Rectangle {
                anchors.centerIn: frame
                visible: !videoItem.playing
                width: Theme.itemSizeLarge
                height: width
                radius: width / 2
                color: Theme.rgba("black", 0.6)
                Image {
                    anchors.centerIn: parent
                    source: "image://theme/icon-l-play?" + "white"
                }
            }
            MouseArea {
                anchors.fill: frame
                enabled: !videoItem.playing
                onPressAndHold: Qt.openUrlExternally(videoItem.block.url || videoItem.block.src)
                onClicked: {
                    if (videoItem.external) {
                        body.app.playEmbed(videoItem.block)
                    } else if (videoItem.noPlayer) {
                        Qt.openUrlExternally(videoItem.block.src)
                    } else {
                        videoItem.playing = true
                    }
                }
            }
            Loader {
                // Plays the video; before that, shows its first frame when it has no picture
                // (the player's own tap starts it then)
                id: player
                anchors.fill: frame
                active: videoItem.playing || videoItem.framePreview
                source: "VideoPlayer.qml"
                onLoaded: {
                    item.autoStart = videoItem.playing
                    item.video = videoItem.block.src
                    item.active = Qt.binding(function () { return body.active })
                }
                // No video support on this phone: let the system play it
                onStatusChanged: {
                    if (status === Loader.Error) {
                        var wanted = videoItem.playing
                        videoItem.noPlayer = true
                        videoItem.playing = false
                        if (wanted) Qt.openUrlExternally(videoItem.block.src)
                    }
                }
            }
            Label {
                id: caption
                anchors { top: frame.bottom; topMargin: Theme.paddingSmall }
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                truncationMode: TruncationMode.Fade
                font.pixelSize: Theme.fontSizeExtraSmall
                color: Theme.secondaryColor
                text: videoItem.external ? qsTr("%1 video · press and hold to open outside the app")
                                           .arg(videoItem.block.site)
                                         : qsTr("Video")
            }
        }
    }

    Component {
        // Videos switched off in Settings: just a link
        id: videoLink
        BackgroundItem {
            readonly property var block: parent ? parent.block : ({})
            height: Theme.itemSizeLarge
            onClicked: Qt.openUrlExternally(block.url || block.src)
            Image {
                id: thumb
                x: Theme.horizontalPageMargin
                anchors.verticalCenter: parent.verticalCenter
                width: status === Image.Ready ? Math.round(height * 16 / 9) : 0
                height: parent.height - 2 * Theme.paddingSmall
                source: parent.block.poster || ""
                sourceSize.height: height
                fillMode: Image.PreserveAspectCrop
                clip: true
                asynchronous: true
            }
            Label {
                anchors { left: thumb.right; leftMargin: thumb.width > 0 ? Theme.paddingMedium : 0
                          right: parent.right; rightMargin: Theme.horizontalPageMargin
                          verticalCenter: parent.verticalCenter }
                truncationMode: TruncationMode.Fade
                font.pixelSize: Theme.fontSizeSmall
                font.underline: true
                color: parent.highlighted ? Theme.highlightColor : Theme.primaryColor
                text: "▶ " + (block.site ? qsTr("%1 video").arg(block.site) : qsTr("Video"))
            }
        }
    }
}
