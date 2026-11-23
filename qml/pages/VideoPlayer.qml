// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// Plays one video file inside the article. Loaded on demand, so a phone without the
// QtMultimedia module still shows articles (the video then opens outside the app).
import QtQuick 2.6
import Sailfish.Silica 1.0
import QtMultimedia 5.6

Item {
    id: player

    property url video
    property bool autoStart: true     // false: show a still frame until tapped
    property bool active: true        // false: the page was left, pause
    property bool previewed: false
    onActiveChanged: if (!active && media.playbackState === MediaPlayer.PlayingState) media.pause()

    function clock(ms) {
        var s = Math.floor(ms / 1000)
        var m = Math.floor(s / 60)
        s = s % 60
        return m + ":" + (s < 10 ? "0" : "") + s
    }

    Video {
        id: media
        anchors.fill: parent
        source: player.video
        autoPlay: player.autoStart
        fillMode: VideoOutput.PreserveAspectFit
        // Preview: pausing makes the player show a frame; one second in rather than the
        // first, which is often black
        onStatusChanged: {
            if (!player.autoStart && !player.previewed && status === MediaPlayer.Loaded) {
                player.previewed = true
                pause()
                seek(duration > 2000 ? 1000 : 0)
            }
        }
    }

    BusyIndicator {
        id: busy
        anchors.centerIn: parent
        size: BusyIndicatorSize.Medium
        running: media.error === MediaPlayer.NoError
                 && (media.status === MediaPlayer.Loading || media.status === MediaPlayer.Buffering
                     || media.status === MediaPlayer.Stalled)
    }

    Rectangle {
        anchors.centerIn: parent
        visible: !busy.running && media.error === MediaPlayer.NoError
                 && media.playbackState !== MediaPlayer.PlayingState
        width: Theme.itemSizeLarge
        height: width
        radius: width / 2
        color: Theme.rgba("black", 0.6)
        Image {
            anchors.centerIn: parent
            source: "image://theme/icon-l-play?" + "white"
        }
    }

    Label {
        anchors.centerIn: parent
        width: parent.width - 2 * Theme.horizontalPageMargin
        visible: media.error !== MediaPlayer.NoError
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        font.pixelSize: Theme.fontSizeExtraSmall
        color: "white"
        text: qsTr("The video cannot be played here (%1). Tap to open it outside the app.")
              .arg(media.errorString)
    }

    MouseArea {
        anchors.fill: parent
        onClicked: {
            if (media.error !== MediaPlayer.NoError) {
                Qt.openUrlExternally(player.video)
            } else if (mouse.y > height - Theme.itemSizeSmall && media.duration > 0) {
                media.seek(media.duration * mouse.x / width)        // tap on the time bar
            } else if (media.playbackState === MediaPlayer.PlayingState) {
                media.pause()
            } else {
                media.play()
            }
        }
    }

    // Time bar along the bottom
    Rectangle {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: Theme.paddingSmall
        color: Theme.rgba("white", 0.25)
        visible: media.duration > 0
        Rectangle {
            height: parent.height
            width: parent.width * Math.min(1, media.position / media.duration)
            color: "white"
        }
    }
    Label {
        anchors { right: parent.right; bottom: parent.bottom
                  margins: Theme.paddingMedium; bottomMargin: Theme.paddingLarge }
        visible: media.duration > 0
        font.pixelSize: Theme.fontSizeExtraSmall
        color: "white"
        text: player.clock(media.position) + " / " + player.clock(media.duration)
    }
}
