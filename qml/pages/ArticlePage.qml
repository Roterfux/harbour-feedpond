// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// One article: the text the feed carries, or the full text read from its web page.
import QtQuick 2.6
import Sailfish.Silica 1.0

Page {
    id: page

    property var app
    property int itemId: 0
    property var article: null        // set when the engine answered
    property bool unread: false       // "Mark as unread" was chosen

    property var full: null           // the full article's blocks, once loaded
    property int fullMinutes: 0       // its reading time
    property string fullSpeech: ""    // its text for reading aloud

    // Reading aloud (Speech Note): the button shows where Speech Note is installed
    readonly property var speaker: app ? app.speaker : null
    readonly property bool canSpeak: app && app.readAloud && speaker !== null
                                     && speaker.available && article !== null
    readonly property bool speaking: speaker !== null && speaker.owner === page
                                     && (speaker.active || speaker.error !== "")

    function readAloud() {
        if (speaking && speaker.active) {
            speaker.release(page)
        } else {
            speaker.speak(showFull ? fullSpeech : article.speech, page)
        }
    }

    Component.onDestruction: if (speaker) speaker.release(page)
    readonly property int minutes: showFull ? fullMinutes
                                 : article && !waitingFull ? article.minutes : 0
    property bool showFull: false     // shown instead of the feed's text
    property bool fullLoading: false
    property string fullError: ""
    property bool autoFull: false     // loaded on opening ("Always open the full article")
    // Until that full article is there, its place stays empty instead of showing the feed's
    // text for a moment
    readonly property bool waitingFull: autoFull && fullLoading

    // Images are scaled to the text width of the upright screen
    readonly property int textWidth: Math.round(Screen.width - 2 * Theme.horizontalPageMargin)

    allowedOrientations: Orientation.All

    function loadFull(again) {
        fullLoading = true
        fullError = ""
        app.call("open_full", [itemId, textWidth, again === true], function (started) {
            if (!started) page.fullLoading = false
        })
    }

    function openFull() {
        if (!app.fullInApp) {
            Qt.openUrlExternally(article.link)
        } else if (full !== null) {
            showFull = true
            flick.scrollToTop()
        } else {
            loadFull(false)
        }
    }

    Component.onCompleted: {
        app.call("open_item", [itemId, textWidth], function (result) {
            if (!result) return
            page.article = result
            page.app.unread = result.unread
            if (page.app.fullInApp && page.app.alwaysFull && result.link !== ""
                    && !result.isVideo) {
                page.autoFull = true
                page.loadFull(false)
            }
        })
    }

    Connections {
        target: app
        onFullArticle: {
            if (itemId !== page.itemId) return
            page.fullLoading = false
            if (result.error) {
                page.fullError = result.error
                page.autoFull = false                       // the feed's text shows instead
            } else {
                page.full = result.blocks
                page.fullMinutes = result.minutes
                page.fullSpeech = result.speech
                page.showFull = true
                if (!page.autoFull) flick.scrollToTop()     // asked for at the bottom
                page.autoFull = false
            }
        }
    }

    // While reading aloud: what is being read, pause/resume and stop
    Rectangle {
        id: readingBar
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: page.speaking ? barContent.height + 2 * Theme.paddingMedium : 0
        visible: height > 0
        color: Theme.rgba(Theme.highlightDimmerColor, 0.9)
        Behavior on height { NumberAnimation { duration: 150 } }

        Item {
            id: barContent
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter
                      leftMargin: Theme.horizontalPageMargin
                      rightMargin: Theme.horizontalPageMargin - Theme.paddingMedium }
            height: Math.max(barText.height, Theme.itemSizeSmall)

            Label {
                id: barText
                anchors { left: parent.left; right: barButtons.left
                          rightMargin: Theme.paddingMedium; verticalCenter: parent.verticalCenter }
                wrapMode: Text.Wrap
                maximumLineCount: 3
                truncationMode: TruncationMode.Elide
                font.pixelSize: Theme.fontSizeExtraSmall
                color: page.speaker && page.speaker.error ? Theme.errorColor : Theme.highlightColor
                text: !page.speaker ? ""
                    : page.speaker.error ? page.speaker.error
                    : page.speaker.starting ? qsTr("Starting Speech Note…")
                    : page.speaker.sentence || qsTr("Reading aloud")
            }
            Row {
                id: barButtons
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                IconButton {
                    visible: page.speaker && page.speaker.task >= 0
                    icon.source: page.speaker && page.speaker.paused
                                 ? "image://theme/icon-m-play" : "image://theme/icon-m-pause"
                    onClicked: page.speaker.paused ? page.speaker.resume() : page.speaker.pause()
                }
                IconButton {
                    icon.source: "image://theme/icon-m-clear"
                    onClicked: page.speaker.release(page)
                }
            }
        }
    }

    SilicaFlickable {
        id: flick
        anchors { left: parent.left; right: parent.right; top: parent.top
                  bottom: readingBar.top }
        clip: true
        contentHeight: column.height + Theme.paddingLarge

        PullDownMenu {
            busy: page.fullLoading
            MenuItem {
                text: page.unread ? qsTr("Mark as read") : qsTr("Mark as unread")
                onClicked: {
                    page.unread = !page.unread
                    page.app.call("set_read", [page.itemId, !page.unread], function (unread) {
                        page.app.unread = unread
                    })
                }
            }
            MenuItem {
                text: qsTr("Open in browser")
                visible: page.article !== null && page.article.link !== ""
                onClicked: Qt.openUrlExternally(page.article.link)
            }
            MenuItem {
                text: qsTr("Share")
                visible: page.article !== null && page.article.link !== ""
                onClicked: page.app.share(page.article.title, page.article.link)
            }
            MenuItem {
                text: page.speaking && page.speaker.active ? qsTr("Stop reading aloud")
                                                           : qsTr("Read aloud")
                visible: page.canSpeak && !page.waitingFull
                onClicked: page.readAloud()
            }
            MenuItem {
                text: qsTr("Load full article again")
                visible: page.showFull
                enabled: !page.fullLoading
                onClicked: page.loadFull(true)
            }
            MenuItem {
                text: page.showFull ? qsTr("Show feed text") : qsTr("Show full article")
                visible: page.full !== null
                onClicked: page.showFull = !page.showFull
            }
        }

        Column {
            id: column
            width: parent.width
            spacing: Theme.paddingMedium

            FeedHeader {
                title: page.article ? page.article.feed : ""
                icon: page.article ? page.article.feedIcon : ""
            }

            Item {
                width: parent.width
                height: Math.max(timeRow.height, shareButton.height)

                IconButton {
                    id: speakButton
                    anchors.right: shareButton.left
                    visible: page.canSpeak && !page.waitingFull
                    icon.source: page.speaking && page.speaker.active
                                 ? "image://theme/icon-m-clear" : "image://theme/icon-m-speaker"
                    onClicked: page.readAloud()
                }

                IconButton {
                    id: shareButton
                    anchors { right: parent.right; rightMargin: Theme.horizontalPageMargin
                                                                - Theme.paddingMedium }
                    visible: page.article !== null && page.article.link !== ""
                    icon.source: "image://theme/icon-m-share"
                    onClicked: page.app.share(page.article.title, page.article.link)
                }

                Row {
                    // Reading time of what is shown: the feed's text or the full article
                    id: timeRow
                    x: Theme.horizontalPageMargin
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Theme.paddingSmall
                    visible: page.minutes > 0
                    Image {
                        anchors.verticalCenter: parent.verticalCenter
                        source: "image://theme/icon-s-time?" + Theme.highlightColor
                    }
                    Label {
                        anchors.verticalCenter: parent.verticalCenter
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.highlightColor
                        text: qsTr("%1 min read").arg(page.minutes)
                              + (page.showFull ? "  ·  " + qsTr("full article")
                                 : page.article && page.article.link !== ""
                                   ? "  ·  " + qsTr("feed text") : "")
                    }
                }
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                font.pixelSize: Theme.fontSizeLarge
                color: Theme.highlightColor
                text: page.article ? page.article.title : ""
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                font.pixelSize: Theme.fontSizeExtraSmall
                color: Theme.secondaryHighlightColor
                text: !page.article ? ""
                    : (page.article.author ? page.article.author + "  ·  " : "")
                      + Format.formatDate(new Date(page.article.published * 1000),
                                          Formatter.TimepointRelative)
            }

            Image {
                // The article's picture when the text carries none (e.g. Media RSS feeds)
                width: parent.width
                height: visible && implicitWidth > 0
                        ? Math.round(width * implicitHeight / implicitWidth) : 0
                visible: status === Image.Ready && !page.showFull && !page.waitingFull
                source: page.article && page.article.lead ? page.article.lead : ""
                sourceSize.width: Screen.width
                fillMode: Image.PreserveAspectFit
                asynchronous: true
            }

            ArticleBody {
                app: page.app
                blocks: page.showFull ? page.full
                      : page.article && !page.waitingFull ? page.article.blocks : []
                active: page.status === PageStatus.Active && Qt.application.active
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                visible: page.fullError !== ""
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.secondaryHighlightColor
                text: qsTr("The full article could not be loaded: %1").arg(page.fullError)
            }

            BusyIndicator {
                anchors.horizontalCenter: parent.horizontalCenter
                size: BusyIndicatorSize.Medium
                running: page.fullLoading
                visible: running
            }

            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: page.article !== null && page.article.link !== "" && !page.fullLoading
                text: page.showFull || page.fullError !== "" ? qsTr("Open in browser")
                                                             : qsTr("Open full article")
                onClicked: {
                    if (page.showFull || page.fullError !== "") {
                        Qt.openUrlExternally(page.article.link)
                    } else {
                        page.openFull()
                    }
                }
            }
        }

        VerticalScrollDecorator {}
    }
}
