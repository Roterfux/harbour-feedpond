// Feedpond - SPDX-License-Identifier: GPL-3.0-or-later
// Reading articles aloud through Speech Note (harbour-dsnote, OpenRepos), which offers its
// text-to-speech on the session bus as org.mkiol.Speech at "/". Optional: without Speech
// Note, `available` stays false and the app shows no read-aloud button.
// The service quits when nobody calls KeepAliveService for 60 s and drops a task without
// KeepAliveTask for 10 s, so a timer keeps both alive while reading.
import QtQuick 2.6
import Nemo.DBus 2.0

Item {
    id: speaker

    property bool available: false    // Speech Note is installed (or running)
    property int task: -1             // what Speech Note is reading for us
    property bool starting: false     // asked, no answer yet
    property bool paused: false
    property string sentence: ""      // the part being read now
    property string error: ""
    property var owner: null          // the article page that asked
    readonly property bool active: task >= 0 || starting

    function check() {
        bus.call("ListActivatableNames", [], function (names) {
            if (names && names.indexOf("org.mkiol.Speech") >= 0) {
                speaker.available = true
            } else {
                bus.call("ListNames", [], function (running) {
                    speaker.available = !!running && running.indexOf("org.mkiol.Speech") >= 0
                })
            }
        }, function (failure) {
            console.log("Read aloud: cannot list D-Bus services:", failure)
        })
    }

    // Speech Note's State property
    readonly property int stateNotConfigured: 1
    readonly property int stateBusy: 2
    readonly property int stateIdle: 3

    property string pendingText: ""   // waits for Speech Note to finish starting
    property int waited: 0            // checks so far
    property int tries: 0             // TtsPlaySpeech attempts

    function speak(text, page) {
        stop()
        owner = page
        error = ""
        sentence = ""
        paused = false
        starting = true
        pendingText = text
        waited = 0
        tries = 0
        // The first call starts the service if it is not running yet; it is "busy" while
        // it loads its models, and refuses to speak until it is idle
        speech.call("KeepAliveService", [], function () { readyCheck.start() }, speaker.failed)
    }

    // -1: could not be read
    function speechState() {
        var value = speech.getProperty("State")
        return value === undefined || value === null ? -1 : Number(value)
    }

    // Text-to-speech models (voices) Speech Note has; -1: could not be read
    function voices() {
        var models = speech.getProperty("TtsModels")
        return models && typeof models === "object" ? Object.keys(models).length : -1
    }

    // Called every half second until Speech Note can speak (or gives up after 30 s)
    function checkReady() {
        if (!starting) {
            readyCheck.stop()
            return
        }
        var now = speechState()
        waited += 1
        if (now === stateNotConfigured || (now === stateIdle && voices() === 0)) {
            readyCheck.stop()
            starting = false
            error = qsTr("Speech Note has no voice for reading aloud. In Speech Note, open "
                         + "Languages, choose a language and download a model under "
                         + "\"Text to Speech\".")
            return
        }
        if (now === stateIdle || waited >= 60) {
            readyCheck.stop()
            play()
        } else if (waited % 10 === 0) {
            speech.call("KeepAliveService", [])
        }
    }

    function play() {
        tries += 1
        speech.call("TtsPlaySpeech", [pendingText, ""], function (taskId) {   // "": default voice
            if (!speaker.starting) return                 // stopped meanwhile
            if (taskId >= 0) {
                speaker.starting = false
                speaker.task = taskId
            } else if (speaker.tries < 3) {
                retry.start()                             // still settling: try again shortly
            } else {
                speaker.starting = false
                speaker.error = qsTr("Speech Note does not read (state %1, %2 voices). Open "
                                     + "Speech Note and check that a \"Text to Speech\" model "
                                     + "is chosen.").arg(speaker.speechState())
                                                    .arg(speaker.voices())
            }
        }, speaker.failed)
    }

    Timer {
        id: readyCheck
        interval: 500
        repeat: true
        triggeredOnStart: true
        onTriggered: speaker.checkReady()
    }

    Timer {
        id: retry
        interval: 1500
        onTriggered: if (speaker.starting) speaker.play()
    }

    // The error callback gets the D-Bus error name and message: show both, they tell
    // a sandbox refusal (AccessDenied) from a missing or failing service
    function failed() {
        var parts = []
        for (var i = 0; i < arguments.length; ++i) {
            if (arguments[i] !== undefined && arguments[i] !== null && String(arguments[i]) !== "")
                parts.push(String(arguments[i]))
        }
        starting = false
        task = -1
        error = qsTr("Speech Note cannot be reached (%1)").arg(parts.length ? parts.join(": ") : "?")
        console.log("Read aloud:", error)
    }

    function taskCall(method) {
        if (task >= 0) speech.typedCall(method, [{ "type": "i", "value": task }])
    }

    function pause() {
        taskCall("TtsPauseSpeech")
        paused = true
    }

    function resume() {
        taskCall("TtsResumeSpeech")
        paused = false
    }

    function stop() {
        taskCall("TtsStopSpeech")
        readyCheck.stop()
        retry.stop()
        task = -1
        starting = false
        paused = false
        sentence = ""
    }

    // Stop only if this page is the one being read
    function release(page) {
        if (owner === page) {
            stop()
            error = ""
            owner = null
        }
    }

    Component.onCompleted: check()

    Timer {
        interval: 5000
        repeat: true
        running: speaker.task >= 0
        onTriggered: {
            speech.call("KeepAliveService", [])
            speaker.taskCall("KeepAliveTask")
        }
    }

    DBusInterface {
        id: bus
        bus: DBus.SessionBus
        service: "org.freedesktop.DBus"
        path: "/org/freedesktop/DBus"
        iface: "org.freedesktop.DBus"
    }

    DBusInterface {
        id: speech
        bus: DBus.SessionBus
        service: "org.mkiol.Speech"
        path: "/"
        iface: "org.mkiol.Speech"
        signalsEnabled: true

        function ttsPlaySpeechFinished(taskId) {
            if (taskId === speaker.task) {
                speaker.task = -1
                speaker.paused = false
                speaker.sentence = ""
            }
        }
        function ttsPartialSpeechPlaying(text, taskId) {
            if (taskId === speaker.task) speaker.sentence = text
        }
    }
}
