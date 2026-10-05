#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

import sys
import tempfile
import unittest
from pathlib import Path

from agent_recorder.Capture import FfmpegLocator, OutputSize, X11GrabCapture
from agent_recorder.Models import CaptureError, FfmpegNotFoundError

from Support import sampleRecording


class CaptureTest(unittest.TestCase):

    def testFitScalesWideFramesAndKeepsTheDefaultSize(self):
        self.assertEqual(OutputSize.fit(1920, 1080), (1280, 720))
        self.assertEqual(OutputSize.fit(1366, 768), (1280, 718))
        self.assertEqual(OutputSize.fit(1280, 800), (1280, 800))
        self.assertEqual(OutputSize.fit(801, 601), (800, 600))

    def testCommandRecordsX11AtFiveFps(self):
        command = X11GrabCapture.buildCommand(
            "ffmpeg",
            ":12",
            Path("clip.mp4"),
            5,
            7200,
            (1280, 800),
            (1280, 800),
        )
        self.assertIn("x11grab", command)
        self.assertNotIn("gdigrab", command)
        self.assertEqual(command[command.index("-framerate") + 1], "5")
        self.assertEqual(command[command.index("-t") + 1], "7200")
        self.assertEqual(command[command.index("-i") + 1], ":12.0")
        self.assertIn("libx264", command)
        self.assertIn("yuv420p", command)
        self.assertIn("+faststart", command)
        self.assertEqual(command[command.index("-crf") + 1], "32")
        self.assertNotIn("-vf", command)

    def testCommandScalesWhenTheDisplayIsLarger(self):
        command = X11GrabCapture.buildCommand(
            "ffmpeg",
            ":12",
            Path("clip.mp4"),
            5,
            30,
            (1920, 1080),
            (1280, 720),
        )
        self.assertEqual(command[command.index("-vf") + 1], "scale=1280:720")

    def testMissingConfiguredBinaryRaises(self):
        with self.assertRaises(FfmpegNotFoundError) as caught:
            FfmpegLocator(r"C:\missing\ffmpeg.exe").resolve()

        self.assertEqual(str(caught.exception), "FFmpeg is required but was not found.")

    def testStartRejectsNonLinux(self):
        if sys.platform == "linux":
            return

        with tempfile.TemporaryDirectory() as directory:
            recording = sampleRecording(Path(directory))
            with self.assertRaises(CaptureError):
                X11GrabCapture(FfmpegLocator()).start(recording)


if __name__ == "__main__":
    unittest.main()
