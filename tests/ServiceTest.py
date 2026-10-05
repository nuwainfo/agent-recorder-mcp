#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from agent_recorder.Cleanup import AfterDownloadCleanup
from agent_recorder.Delivery import DeliveryFactory, LocalDelivery
from agent_recorder.Models import (
    CleanupPolicy,
    DeliveryError,
    DeliveryKind,
    DisplayNotFoundError,
    FfmpegNotFoundError,
    RecorderError,
    RecordingState,
)
from agent_recorder.Service import RecorderConfig, RecordingService
from agent_recorder.Store import RecordingStore

from Support import (
    FIXED_NOW,
    PLAYABLE_BYTES,
    FakeCapture,
    FakeClock,
    FakeDelivery,
    FakeDiscovery,
    FakeInspector,
    openService,
    sampleRecording,
)


class ServiceTest(unittest.TestCase):

    def testStartUsesFiveFpsAndASecondStartReturnsTheSameRecording(self):
        with tempfile.TemporaryDirectory() as directory:
            discovery = FakeDiscovery()
            service, store, _delivery, capture = openService(Path(directory), discovery=discovery)
            first = service.start()
            second = service.start()
            self.assertEqual(first.recording.recordingId, second.recording.recordingId)
            self.assertFalse(first.alreadyRecording)
            self.assertTrue(second.alreadyRecording)
            self.assertEqual(capture.started, [":12"])
            self.assertEqual(first.recording.fps, 5)
            payload = service.payloadFor(first.recording, alreadyRecording=second.alreadyRecording)
            self.assertIn("recordingId", payload)
            self.assertNotIn("recording_id", payload)
            self.assertEqual(payload["state"], "recording")
            self.assertTrue(payload["alreadyRecording"])
            disk = store.load(first.recording.recordingId)
            self.assertEqual(disk.fps, 5)
            self.assertEqual(disk.display, ":12")

    def testInvalidFpsFailsBeforeDiscovery(self):
        with tempfile.TemporaryDirectory() as directory:
            discovery = FakeDiscovery()
            service, _store, _delivery, _capture = openService(Path(directory), discovery=discovery)
            with self.assertRaises(ValueError):
                service.start(fps=True)

            self.assertEqual(discovery.calls, 0)

    def testMissingFfmpegFailsBeforeDiscovery(self):
        with tempfile.TemporaryDirectory() as directory:
            discovery = FakeDiscovery()
            capture = FakeCapture(failAvailability=True)
            service, _store, _delivery, _capture = openService(
                Path(directory),
                discovery=discovery,
                capture=capture,
            )
            with self.assertRaises(FfmpegNotFoundError):
                service.start()

            self.assertEqual(discovery.calls, 0)

    def testMissingDisplayDoesNotStartCapture(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = FakeCapture()
            service, _store, _delivery, _capture = openService(
                Path(directory),
                discovery=FakeDiscovery(error=DisplayNotFoundError()),
                capture=capture,
            )
            with self.assertRaises(DisplayNotFoundError):
                service.start()

            self.assertEqual(capture.started, [])

    def testFinishKeepsTheFileUntilTheDownloadCompletes(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _store, delivery, capture = openService(Path(directory))
            started = service.start()
            finished = service.finish()
            self.assertEqual(finished.state, RecordingState.SHARED)
            self.assertEqual(finished.url, "https://fastfilelink.example/replay")
            self.assertEqual(finished.cleanup, CleanupPolicy.AFTER_DOWNLOAD)
            self.assertTrue(finished.outputPath.exists())
            self.assertFalse(delivery.session.stopped)
            delivery.session.emitCompleted()
            self.assertFalse(finished.outputPath.exists())
            self.assertTrue(delivery.session.stopped)
            self.assertEqual(finished.state, RecordingState.CLEANED)
            started.recording.watchThread.join(2)
            self.assertFalse(started.recording.watchThread.is_alive())
            self.assertEqual(capture.handle.stopCalls, 1)

    def testLocalManualDeliveryLeavesTheFile(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _store, _delivery, _capture = openService(Path(directory))
            service.start()
            finished = service.finish(delivery=DeliveryKind.LOCAL, cleanup=CleanupPolicy.MANUAL)
            self.assertTrue(finished.outputPath.exists())
            self.assertTrue(finished.url.startswith("file:"))
            self.assertEqual(finished.state, RecordingState.SHARED)

    def testAfterUploadIsRejectedWithoutStopping(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _store, _delivery, capture = openService(Path(directory))
            service.start()
            with self.assertRaises(DeliveryError) as caught:
                service.finish(cleanup=CleanupPolicy.AFTER_UPLOAD)

            self.assertIn("after_upload is not available", str(caught.exception))
            self.assertTrue(capture.handle.running)

    def testAfterDownloadRequiresFfl(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _store, _delivery, capture = openService(Path(directory))
            service.start()
            with self.assertRaises(DeliveryError):
                service.finish(delivery=DeliveryKind.LOCAL, cleanup=CleanupPolicy.AFTER_DOWNLOAD)

            self.assertTrue(capture.handle.running)

    def testAbortDeletesByDefaultAndCanKeepThePartialFile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, _store, _delivery, _capture = openService(root)
            service.start()
            aborted = service.abort(deletePartial=False)
            self.assertEqual(aborted.state, RecordingState.ABORTED)
            self.assertTrue(aborted.outputPath.exists())

            service, _store, _delivery, _capture = openService(root / "second")
            service.start()
            aborted = service.abort()
            self.assertFalse(aborted.outputPath.exists())
            self.assertIsNone(service.status())

    def testCleanupDeletesTheFile(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _store, _delivery, _capture = openService(Path(directory))
            started = service.start()
            cleaned = service.cleanup(started.recording.recordingId)
            started.recording.watchThread.join(2)
            self.assertFalse(started.recording.watchThread.is_alive())
            self.assertEqual(cleaned.state, RecordingState.CLEANED)
            self.assertFalse(cleaned.outputPath.exists())

    def testTimeoutLeavesAReadyFileThatFinishCanShare(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _store, delivery, capture = openService(Path(directory))
            started = service.start()
            capture.handle.expire(0, True)
            started.recording.watchThread.join(2)
            self.assertEqual(service.status().state, RecordingState.READY)
            finished = service.finish()
            self.assertEqual(finished.url, delivery.session.link)
            self.assertEqual(capture.handle.stopCalls, 0)

    def testOrphanFfmpegIsStoppedWhenItsOwnerIsGone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording = sampleRecording(root)
            inspector = FakeInspector(alive={77})
            _service, store = self._recover(root, recording, inspector)
            self.assertEqual(inspector.interrupted, [77])
            self.assertEqual(store.load(recording.recordingId).state, RecordingState.FAILED)

    def testLiveOwnerIsLeftAloneUntilTheTimeLimit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording = sampleRecording(root)
            inspector = FakeInspector(alive={77, 88})
            _service, store = self._recover(root, recording, inspector)
            self.assertEqual(inspector.interrupted, [])
            self.assertEqual(store.load(recording.recordingId).state, RecordingState.RECORDING)

    def testExpiredCaptureIsStoppedEvenIfTheOwnerIsAlive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording = sampleRecording(root)
            inspector = FakeInspector(alive={77, 88})
            clock = FakeClock(FIXED_NOW + timedelta(seconds=7200))
            _service, store = self._recover(root, recording, inspector, clock=clock, playable=True)
            self.assertEqual(inspector.interrupted, [77])
            self.assertEqual(store.load(recording.recordingId).state, RecordingState.READY)

    def testDeadFfmpegIsMarkedFailedWithoutAnInterrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording = sampleRecording(root)
            inspector = FakeInspector()
            _service, store = self._recover(root, recording, inspector)
            self.assertEqual(inspector.interrupted, [])
            self.assertEqual(store.load(recording.recordingId).state, RecordingState.FAILED)

    def testInterruptedShareCanBeSharedAgain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording = sampleRecording(
                root,
                state=RecordingState.SHARED,
                url="https://fastfilelink.example/old",
            )
            _service, store = self._recover(root, recording, FakeInspector(), playable=True)
            loaded = store.load(recording.recordingId)
            self.assertEqual(loaded.state, RecordingState.READY)
            self.assertIsNone(loaded.url)

    def testLiveShareIsNotReset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording = sampleRecording(
                root,
                state=RecordingState.SHARED,
                url="https://fastfilelink.example/old",
            )
            _service, store = self._recover(root, recording, FakeInspector(alive={88}), playable=True)
            loaded = store.load(recording.recordingId)
            self.assertEqual(loaded.state, RecordingState.SHARED)
            self.assertEqual(loaded.url, "https://fastfilelink.example/old")

    def testFinishRefusesAnotherLiveRecorder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording = sampleRecording(root, state=RecordingState.READY, ffmpegPid=None)
            service, _store = self._recover(root, recording, FakeInspector(alive={88}), playable=True)
            with self.assertRaises(RecorderError):
                service.finish(recording.recordingId)

    def _recover(self, root, recording, inspector, clock=None, playable=False):
        if playable:
            recording.outputPath.parent.mkdir(parents=True, exist_ok=True)
            recording.outputPath.write_bytes(PLAYABLE_BYTES)

        config = RecorderConfig(root, None)
        store = RecordingStore(config.recordingsDir)
        store.save(recording)
        service = RecordingService(
            config=config,
            discovery=FakeDiscovery(),
            capture=FakeCapture(),
            deliveries=DeliveryFactory({
                DeliveryKind.FFL: FakeDelivery(),
                DeliveryKind.LOCAL: LocalDelivery(),
            }),
            cleanup=AfterDownloadCleanup(),
            store=store,
            clock=clock if clock is not None else FakeClock(),
            inspector=inspector,
        )
        return service, store


if __name__ == "__main__":
    unittest.main()
