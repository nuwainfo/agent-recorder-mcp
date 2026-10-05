#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
import unittest
from pathlib import Path

from agent_recorder.Models import CleanupPolicy, DeliveryKind, RecordingNotFoundError, RecordingState
from agent_recorder.Store import RecordingStore

from Support import sampleRecording


class StoreTest(unittest.TestCase):

    def testRoundTripUsesSnakeCaseOnDisk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RecordingStore(root)
            recording = sampleRecording(
                root,
                cleanup=CleanupPolicy.AFTER_DOWNLOAD,
                delivery=DeliveryKind.FFL,
                url="https://fastfilelink.example/replay",
            )
            store.save(recording)
            payload = json.loads((root / f"{recording.recordingId}.json").read_text(encoding="utf-8"))
            self.assertIn("recording_id", payload)
            self.assertNotIn("recordingId", payload)
            self.assertEqual(payload["state"], "recording")
            self.assertEqual(payload["cleanup"], "after_download")
            loaded = store.load(recording.recordingId)
            self.assertEqual(loaded.state, RecordingState.RECORDING)
            self.assertEqual(loaded.delivery, DeliveryKind.FFL)
            self.assertEqual(loaded.startedAt, recording.startedAt)

    def testRejectsAPathLikeRecordingId(self):
        store = RecordingStore(Path("."))
        with self.assertRaises(RecordingNotFoundError):
            store.load("../secret")


if __name__ == "__main__":
    unittest.main()
