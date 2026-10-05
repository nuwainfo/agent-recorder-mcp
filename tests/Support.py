#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import threading

from datetime import datetime, timedelta, timezone

from agent_recorder.Cleanup import AfterDownloadCleanup
from agent_recorder.Delivery import DeliveryFactory, DeliveryResult, LocalDelivery
from agent_recorder.Display import FrameView, ProcessSnapshot
from agent_recorder.Models import (
    CaptureError,
    DeliveryKind,
    FfmpegNotFoundError,
    Recording,
    RecordingState,
)
from agent_recorder.Service import RecorderConfig, RecordingService
from agent_recorder.Store import RecordingStore


FIXED_NOW = datetime(2026, 10, 5, 17, 30, tzinfo=timezone(timedelta(hours=8)))
PLAYABLE_BYTES = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x08moov"
PARTIAL_BYTES = b"\x00\x00\x00\x18ftypisom"


class FakeClock:
    def __init__(self, now=FIXED_NOW):
        self._now = now

    def now(self):
        return self._now

    def advance(self, seconds):
        self._now = self._now + timedelta(seconds=seconds)


class FakeInspector:
    def __init__(self, alive=()):
        self._alive = set(alive)
        self.interrupted = []

    def isAlive(self, pid):
        return pid in self._alive

    def interrupt(self, pid):
        self.interrupted.append(pid)
        self._alive.discard(pid)

    def waitUntilExit(self, pid, timeout):
        del timeout
        return pid not in self._alive


class FakeHandle:
    def __init__(self, outputPath, logPath):
        self.outputPath = outputPath
        self.logPath = logPath
        self.pid = 4242
        self.returnCode = None
        self.stopCalls = 0
        self._stderr = ""
        self._stopped = threading.Event()

    @property
    def running(self):
        return not self._stopped.is_set()

    def stop(self, timeout):
        del timeout
        self.stopCalls += 1
        self.outputPath.parent.mkdir(parents=True, exist_ok=True)
        self.outputPath.write_bytes(PLAYABLE_BYTES)
        self.returnCode = 0
        self._stopped.set()

    def expire(self, returnCode, playable):
        self.outputPath.parent.mkdir(parents=True, exist_ok=True)
        self.outputPath.write_bytes(PLAYABLE_BYTES if playable else PARTIAL_BYTES)
        self.returnCode = returnCode
        self._stopped.set()

    def wait(self, timeout=None):
        self._stopped.wait(timeout)
        return self.returnCode

    def stderrText(self):
        return self._stderr


class FakeCapture:
    def __init__(self, failAvailability=False, failStart=False):
        self.failAvailability = failAvailability
        self.failStart = failStart
        self.started = []
        self.handle = None

    def ensureAvailable(self):
        if self.failAvailability:
            raise FfmpegNotFoundError()

        return "ffmpeg"

    def start(self, recording):
        if self.failStart:
            raise CaptureError("ffmpeg failed")

        self.started.append(recording.display)
        handle = FakeHandle(recording.outputPath, recording.logPath)
        self.handle = handle
        return handle

    def stop(self, handle):
        handle.stop(5)


class FakeDiscovery:
    def __init__(self, display=":12", error=None):
        self.display = display
        self.error = error
        self.calls = 0

    def identify(self):
        self.calls += 1
        if self.error is not None:
            raise self.error

        return self.display


class FakeShareSession:
    def __init__(self):
        self.link = "https://fastfilelink.example/replay"
        self.stopped = False
        self._listeners = []

    def on(self, name, listener):
        self._listeners.append((name, listener))

    def stop(self, timeout=5):
        del timeout
        self.stopped = True

    def emitCompleted(self):
        for name, listener in list(self._listeners):
            if name == "completed":
                listener(object())


class FakeDelivery:
    def __init__(self):
        self.session = FakeShareSession()
        self.calls = []

    def deliver(self, recording):
        self.calls.append(recording.outputPath)
        return DeliveryResult(url=self.session.link, session=self.session)


class FakeCatalog:
    def __init__(self, displays):
        self._displays = list(displays)

    def listDisplays(self):
        return list(self._displays)


class FakeProbe:
    def __init__(self, readable=None, blank=None):
        self.calls = []
        self._readable = {} if readable is None else readable
        self._blank = {} if blank is None else blank

    def probe(self, display):
        self.calls.append(display)
        return FrameView(
            self._readable.get(display, True),
            self._blank.get(display, False),
        )


class FakeProcessTable:
    def __init__(self, processes, currentPid):
        self._processes = list(processes)
        self._currentPid = currentPid

    def listProcesses(self):
        return list(self._processes)

    def currentPid(self):
        return self._currentPid


def process(pid, ppid, name, display, command=""):
    return ProcessSnapshot(pid, ppid, pid, name, command or name, display)


def sampleRecording(root, **overrides):
    recordingId = overrides.get("recordingId", "rec_20261005_173000_abc123")
    values = dict(
        recordingId=recordingId,
        state=RecordingState.RECORDING,
        display=":12",
        fps=5,
        startedAt=FIXED_NOW,
        maxDurationSeconds=7200,
        outputPath=root / "recordings" / f"{recordingId}.mp4",
        logPath=root / "recordings" / f"{recordingId}.log",
        ffmpegPid=77,
        mcpPid=88,
        cleanup=None,
        delivery=None,
        url=None,
        error=None,
    )
    values.update(overrides)
    return Recording(**values)


def openService(root, discovery=None, capture=None, delivery=None, inspector=None, clock=None):
    config = RecorderConfig(root, None)
    store = RecordingStore(config.recordingsDir)
    if delivery is None:
        delivery = FakeDelivery()

    if capture is None:
        capture = FakeCapture()

    service = RecordingService(
        config=config,
        discovery=discovery if discovery is not None else FakeDiscovery(),
        capture=capture,
        deliveries=DeliveryFactory({
            DeliveryKind.FFL: delivery,
            DeliveryKind.LOCAL: LocalDelivery(),
        }),
        cleanup=AfterDownloadCleanup(),
        store=store,
        clock=clock if clock is not None else FakeClock(),
        inspector=inspector if inspector is not None else FakeInspector(),
    )
    return service, store, delivery, capture
