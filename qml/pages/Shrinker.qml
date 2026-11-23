// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// Shrinks pictures saved for offline reading: Qt decodes them 720 pixels wide and saves
// them as JPEG (Python on the phone has no image library). The engine asks with its
// "shrink" event and keeps the copy if it is smaller (backend.shrunk). PNG and WebP become
// JPEG too, on a plain background where they are transparent: photos sent as PNG are the
// biggest files. Lives outside the visible window; one picture at a time.
import QtQuick 2.6
import Sailfish.Silica 1.0

Item {
    id: shrinker

    property var app
    property var queue: []
    property string current: ""       // the picture being shrunk
    property string kind: ""          // jpg, png or webp

    readonly property int pictureWidth: 720

    x: -100000                        // never on screen, but rendered (grabbing needs that)
    width: picture.width
    height: picture.height

    function add(path, pictureKind) {
        queue.push({ "path": path, "kind": pictureKind })
        if (current === "") next()
    }

    function next() {
        watchdog.stop()
        if (queue.length === 0) {
            current = ""
            return
        }
        var job = queue.shift()
        kind = job.kind
        current = job.path
        watchdog.restart()
    }

    function save() {
        var path = current
        var small = path + ".small.jpg"
        var started = sheet.grabToImage(function (result) {
            if (result.saveToFile(small)) app.call("shrunk", [path, small])
            shrinker.next()
        })
        if (!started) next()          // e.g. the window is not shown: keep the original
    }

    // What is saved: the picture on a plain background (JPEG has no transparency)
    Rectangle {
        id: sheet
        width: picture.width
        height: picture.height
        color: "white"

        Image {
            id: picture
            width: implicitWidth
            height: implicitHeight
            asynchronous: true
            cache: false
            source: shrinker.current !== "" ? "file://" + shrinker.current : ""
            sourceSize.width: shrinker.pictureWidth
            onStatusChanged: {
                if (status === Image.Ready) shrinker.save()
                else if (status === Image.Error) shrinker.next()
            }
        }
    }

    // A picture Qt cannot read, or a grab that never answers, must not stop the queue
    Timer {
        id: watchdog
        interval: 20000
        onTriggered: shrinker.next()
    }
}
