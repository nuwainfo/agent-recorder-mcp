#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

import inspect
import tempfile
import unittest
from pathlib import Path

from agent_recorder import MCP

from Support import openService


class ToolSignatureTest(unittest.TestCase):

    def tearDown(self):
        MCP.hub.use(None)

    def _params(self, tool):
        function = tool.fn if hasattr(tool, "fn") else tool
        return inspect.signature(function).parameters

    def _call(self, tool, *args, **kwargs):
        function = tool.fn if hasattr(tool, "fn") else tool
        return function(*args, **kwargs)

    def testPublicTools(self):
        for name in (
            "startRecording",
            "recordingStatus",
            "finishRecording",
            "abortRecording",
            "confirmUpload",
            "cleanupRecording",
        ):
            self.assertTrue(hasattr(MCP, name))

    def testStartDefaults(self):
        params = self._params(MCP.startRecording)
        self.assertEqual(params["fps"].default, 5)
        self.assertEqual(params["maxDurationSeconds"].default, 7200)

    def testFinishDefaults(self):
        params = self._params(MCP.finishRecording)
        self.assertIn("recordingId", params)
        self.assertEqual(params["delivery"].default, "ffl")
        self.assertEqual(params["cleanup"].default, "after_download")

    def testConfirmUploadRequiresAnIdAndUrl(self):
        params = self._params(MCP.confirmUpload)
        self.assertIs(params["recordingId"].default, inspect.Parameter.empty)
        self.assertIs(params["url"].default, inspect.Parameter.empty)

    def testCleanupRequiresAnId(self):
        params = self._params(MCP.cleanupRecording)
        self.assertIs(params["recordingId"].default, inspect.Parameter.empty)

    def testStatusIsIdleWhenNothingIsRecording(self):
        with tempfile.TemporaryDirectory() as directory:
            service, _store, _delivery, _capture = openService(Path(directory))
            MCP.hub.use(service)
            self.assertEqual(self._call(MCP.recordingStatus), {"state": "idle"})


if __name__ == "__main__":
    unittest.main()
