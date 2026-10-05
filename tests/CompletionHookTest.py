#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import unittest
import urllib.request

from agent_recorder.CompletionHook import CompletionHook


class CompletionHookTest(unittest.TestCase):

    def _post(self, hook: CompletionHook, eventName: str) -> int:
        body = json.dumps({"event": eventName, "data": {}}).encode("utf-8")
        request = urllib.request.Request(
            hook.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
            return response.status

    def testDownloadCompleteAnswers200AndRunsOnce(self):
        hook = CompletionHook()
        try:
            arrived = threading.Event()
            calls = []

            def onCompleted():
                calls.append("done")
                arrived.set()

            hook.onComplete(onCompleted)
            self.assertEqual(self._post(hook, "/download/progress"), 200)
            self.assertFalse(arrived.wait(0.2))
            self.assertEqual(self._post(hook, "/download/complete"), 200)
            self.assertTrue(arrived.wait(2))
            self.assertEqual(self._post(hook, "/webrtc/transfer/complete"), 200)
            self.assertEqual(calls, ["done"])
        finally:
            hook.close()

    def testLateListenerSeesAnExistingCompletion(self):
        hook = CompletionHook()
        try:
            self.assertEqual(self._post(hook, "/webrtc/transfer/complete"), 200)
            self.assertTrue(hook.completed)
            seen = []
            hook.onComplete(lambda: seen.append("late"))
            self.assertEqual(seen, ["late"])
        finally:
            hook.close()


if __name__ == "__main__":
    unittest.main()
