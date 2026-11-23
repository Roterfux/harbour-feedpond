// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick 2.6
import Sailfish.Silica 1.0

Page {
    id: page

    property var app

    // Speech Note may have been installed since the start
    Component.onCompleted: if (app.speaker) app.speaker.check()

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height + Theme.paddingLarge

        Column {
            id: column
            width: parent.width

            PageHeader { title: qsTr("Settings") }

            TextSwitch {
                text: qsTr("Mark as read when scrolling")
                description: qsTr("Articles that leave the top of a list while you scroll "
                                  + "down are marked as read.")
                automaticCheck: false
                checked: page.app.markOnScroll
                onClicked: page.app.markOnScroll = !page.app.markOnScroll
            }

            TextSwitch {
                text: qsTr("Hide read articles")
                description: qsTr("Lists show only unread articles; an article you read leaves "
                                  + "the list when you come back to it.")
                automaticCheck: false
                checked: page.app.unreadOnly
                onClicked: page.app.unreadOnly = !page.app.unreadOnly
            }

            TextSwitch {
                text: qsTr("Justified text")
                description: qsTr("Article text lines up on the left and the right edge.")
                automaticCheck: false
                checked: page.app.justify
                onClicked: page.app.justify = !page.app.justify
            }

            TextSwitch {
                text: qsTr("Offline reading")
                description: qsTr("After each update, the full text and the pictures of all "
                                  + "unread articles are downloaded, so they open without a "
                                  + "connection. Uses more data and storage. \"Download for "
                                  + "offline\" in the pull-down menu does it once.")
                automaticCheck: false
                checked: page.app.offline
                onClicked: page.app.offline = !page.app.offline
            }

            TextSwitch {
                text: qsTr("Pictures in article lists")
                description: qsTr("Show each article's picture next to its title. "
                                  + "The pictures are downloaded while you scroll.")
                automaticCheck: false
                checked: page.app.listImages
                onClicked: page.app.listImages = !page.app.listImages
            }

            TextSwitch {
                text: qsTr("Full articles in the app")
                description: qsTr("\"Open full article\" loads the article's web page and shows "
                                  + "its text here, without menus and ads. Off: the page opens "
                                  + "in the browser.")
                automaticCheck: false
                checked: page.app.fullInApp
                onClicked: page.app.fullInApp = !page.app.fullInApp
            }

            TextSwitch {
                text: qsTr("Always open the full article")
                description: qsTr("Every article is loaded from its web page as soon as you "
                                  + "open it. The feed's text stays in the pull-down menu.")
                enabled: page.app.fullInApp
                automaticCheck: false
                checked: page.app.alwaysFull && page.app.fullInApp
                onClicked: page.app.alwaysFull = !page.app.alwaysFull
            }

            TextSwitch {
                text: qsTr("Read aloud")
                description: (page.app.speaker && page.app.speaker.available
                              ? qsTr("Speech Note is installed.")
                              : qsTr("Needs the app Speech Note (OpenRepos) with a voice "
                                     + "downloaded; not found on this phone."))
                             + " " + qsTr("A speaker button on each article reads it with "
                                          + "Speech Note's default voice.")
                automaticCheck: false
                checked: page.app.readAloud
                onClicked: page.app.readAloud = !page.app.readAloud
            }

            TextSwitch {
                text: qsTr("Videos in articles")
                description: qsTr("Show videos with their picture. Video files play in the "
                                  + "article, YouTube and Vimeo on a page of their own, with "
                                  + "sound. Press and hold a video to open it outside the app. "
                                  + "Off: only a link.")
                automaticCheck: false
                checked: page.app.videos
                onClicked: page.app.videos = !page.app.videos
            }
        }

        VerticalScrollDecorator {}
    }
}
