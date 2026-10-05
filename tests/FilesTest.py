#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path

from agent_recorder.Files import RecordingFile

from Support import PLAYABLE_BYTES, sampleRecording


class FilesTest(unittest.TestCase):

    def testPlayableRequiresFtypAndMoov(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            self.assertFalse(RecordingFile.isPlayable(path))
            path.write_bytes(b"\x00" * 32)
            self.assertFalse(RecordingFile.isPlayable(path))
            path.write_bytes(PLAYABLE_BYTES)
            self.assertTrue(RecordingFile.isPlayable(path))

    def testMoovAtTheTailStillCounts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"ftyp" + (b"\x00" * RecordingFile.HEAD_BYTES) + b"moov")
            self.assertTrue(RecordingFile.isPlayable(path))

    def testDeleteMediaRemovesTheFileAndIgnoresAMissingOne(self):
        with tempfile.TemporaryDirectory() as directory:
            recording = sampleRecording(Path(directory))
            recording.outputPath.parent.mkdir(parents=True)
            recording.outputPath.write_bytes(PLAYABLE_BYTES)
            RecordingFile.deleteMedia(recording)
            self.assertFalse(recording.outputPath.exists())
            RecordingFile.deleteMedia(recording)


if __name__ == "__main__":
    unittest.main()
