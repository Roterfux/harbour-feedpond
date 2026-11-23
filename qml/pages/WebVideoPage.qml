// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// A YouTube or Vimeo video, played by the site's own player in a web view (with sound,
// full screen when the phone is turned). Opened through app.playEmbed, which falls back to
// the browser when the phone has no web view for apps.
import QtQuick 2.6
import Sailfish.Silica 1.0
import Sailfish.WebView 1.0

WebViewPage {
    id: page

    property var app
    property string url               // the page that plays the video
    property string link              // the video's own page, for the browser

    allowedOrientations: Orientation.All

    // Leaving the page (swipe back) destroys it, which ends the playback
    WebView {
        anchors.fill: parent
        url: page.url
    }
}
