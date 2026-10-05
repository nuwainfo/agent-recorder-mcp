#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path

from agent_recorder.Delivery import FFLDelivery, GoogleDriveDelivery, LocalDelivery
from agent_recorder.Models import DeliveryError

from Support import FakeCompletionHook, sampleRecording


class _Session:
    def __init__(self, link, captured):
        self.link = link
        self.captured = captured


def _share(path, **kwargs):
    session = _Session("https://fastfilelink.example/abc", {"path": path, "kwargs": kwargs})
    return session


class DeliveryTest(unittest.TestCase):

    def testFflShareUsesOurCompletionHook(self):
        with tempfile.TemporaryDirectory() as directory:
            recording = sampleRecording(Path(directory))
            hook = FakeCompletionHook()
            result = FFLDelivery(_share, hookFactory=lambda: hook).deliver(recording)
            self.assertEqual(result.url, "https://fastfilelink.example/abc")
            self.assertEqual(result.session.captured["path"], str(recording.outputPath))
            self.assertEqual(result.session.captured["kwargs"]["name"], recording.outputPath.name)
            self.assertFalse(result.session.captured["kwargs"]["capture_hook_events"])
            self.assertEqual(result.session.captured["kwargs"]["hook_url"], hook.url)
            self.assertIs(result.completionHook, hook)

    def testFflShareWithoutALinkFails(self):
        with tempfile.TemporaryDirectory() as directory:
            recording = sampleRecording(Path(directory))
            hook = FakeCompletionHook()

            def share(path, **kwargs):
                del path, kwargs
                return _Session("", {})

            with self.assertRaises(DeliveryError):
                FFLDelivery(share, hookFactory=lambda: hook).deliver(recording)

            self.assertTrue(hook.closed)

    def testLocalDeliveryReturnsAFileUri(self):
        with tempfile.TemporaryDirectory() as directory:
            recording = sampleRecording(Path(directory))
            result = LocalDelivery().deliver(recording)
            self.assertTrue(result.url.startswith("file:"))
            self.assertIsNone(result.session)

    def testGoogleDriveDeliveryWaitsForTheConnector(self):
        with tempfile.TemporaryDirectory() as directory:
            recording = sampleRecording(Path(directory))
            result = GoogleDriveDelivery().deliver(recording)
            self.assertIsNone(result.url)
            self.assertTrue(result.awaitsUpload)
            self.assertIsNone(result.session)


if __name__ == "__main__":
    unittest.main()
