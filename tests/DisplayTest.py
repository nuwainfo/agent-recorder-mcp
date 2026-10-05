#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path

from agent_recorder.Display import (
    AgentDisplayDiscovery,
    FrameStats,
    LinuxProcessTable,
    X11Display,
    X11SocketCatalog,
)
from agent_recorder.Models import DisplayNotFoundError

from Support import FakeCatalog, FakeProbe, FakeProcessTable, process


class DisplayTest(unittest.TestCase):

    def _discovery(self, processes, currentPid, displays, readable=None, blank=None):
        probe = FakeProbe(readable=readable, blank=blank)
        discovery = AgentDisplayDiscovery(
            FakeProcessTable(processes, currentPid),
            FakeCatalog(displays),
            probe,
        )
        return discovery, probe

    def testBrowserDisplayWinsOverInheritedDisplayAndIgnoresOtherAgent(self):
        processes = [
            process(1, 0, "systemd", None),
            process(5, 1, "agent", ":12"),
            process(6, 5, "uvx", None),
            process(7, 6, "python", ":0"),
            process(8, 5, "chrome", ":12", "google-chrome"),
            process(20, 1, "chrome", ":33", "google-chrome"),
        ]
        discovery, probe = self._discovery(processes, 7, [":0", ":12", ":33"])
        self.assertEqual(discovery.identify(), ":12")
        self.assertEqual(probe.calls, [":12"])

    def testBlankAttributedDisplayIsStillSelected(self):
        processes = [
            process(7, 5, "python", ":12"),
            process(5, 1, "agent", None),
        ]
        discovery, probe = self._discovery(
            processes,
            7,
            [":0", ":12"],
            blank={":12": True},
        )
        self.assertEqual(discovery.identify(), ":12")
        self.assertEqual(probe.calls, [":12"])

    def testUnreadableDisplayFails(self):
        processes = [
            process(7, 5, "python", ":12"),
            process(5, 1, "agent", None),
        ]
        discovery, _probe = self._discovery(
            processes,
            7,
            [":12"],
            readable={":12": False},
        )
        with self.assertRaises(DisplayNotFoundError) as caught:
            discovery.identify()

        self.assertEqual(str(caught.exception), "No active agent display could be identified.")

    def testDoesNotUseADisplayOutsideTheAgentTree(self):
        processes = [
            process(7, 5, "python", None),
            process(5, 1, "agent", None),
            process(50, 1, "chrome", ":0", "google-chrome"),
        ]
        discovery, probe = self._discovery(processes, 7, [":0"])
        with self.assertRaises(DisplayNotFoundError):
            discovery.identify()

        self.assertEqual(probe.calls, [])

    def testNearestAncestorDisplayIsUsedWhenNoBrowserIsOpen(self):
        processes = [
            process(7, 5, "python", None),
            process(5, 1, "agent", ":11"),
        ]
        discovery, _probe = self._discovery(processes, 7, [":0", ":11"])
        self.assertEqual(discovery.identify(), ":11")

    def testDisplayMissingFromSocketsFails(self):
        processes = [
            process(7, 5, "python", ":12"),
            process(5, 1, "agent", None),
        ]
        discovery, probe = self._discovery(processes, 7, [":0"])
        with self.assertRaises(DisplayNotFoundError):
            discovery.identify()

        self.assertEqual(probe.calls, [])

    def testDisagreeingBrowsersFail(self):
        processes = [
            process(5, 1, "agent", None),
            process(7, 5, "python", ":12"),
            process(8, 5, "chrome", ":12", "google-chrome"),
            process(9, 5, "firefox", ":14", "firefox"),
        ]
        discovery, probe = self._discovery(processes, 7, [":12", ":14"])
        with self.assertRaises(DisplayNotFoundError):
            discovery.identify()

        self.assertEqual(probe.calls, [])

    def testScreenSuffixMatchesSocketName(self):
        processes = [
            process(7, 5, "python", ":12.0"),
            process(5, 1, "agent", None),
        ]
        discovery, _probe = self._discovery(processes, 7, [":12"])
        self.assertEqual(discovery.identify(), ":12")

    def testParseStatAllowsParenthesesInTheProcessName(self):
        name, ppid, sid = LinuxProcessTable.parseStat("42 (chrome (gpu)) S 7 7 9 0 0")
        self.assertEqual(name, "chrome (gpu)")
        self.assertEqual(ppid, 7)
        self.assertEqual(sid, 9)

    def testDisplayFromEnvironIgnoresOtherVariables(self):
        raw = b"SECRET=abc\0DISPLAY=:12\0PATH=/bin\0"
        self.assertEqual(LinuxProcessTable.displayFromEnviron(raw), ":12")

    def testNormalizeAndGrabTarget(self):
        self.assertEqual(X11Display.normalize(":12.0"), ":12")
        self.assertEqual(X11Display.normalize("localhost:12.0"), "localhost:12")
        self.assertEqual(X11Display.grabTarget(":12"), ":12.0")
        self.assertEqual(X11Display.grabTarget(":12.0"), ":12.0")

    def testFlatFrameIsBlankAndNoisyFrameIsNot(self):
        self.assertTrue(FrameStats.isBlank(bytes(64)))
        noisy = bytes(index % 256 for index in range(256))
        self.assertFalse(FrameStats.isBlank(noisy))

    def testSocketCatalogReadsXSocketsOnly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "X0").write_text("", encoding="utf-8")
            (root / "X12").write_text("", encoding="utf-8")
            (root / "notes").write_text("", encoding="utf-8")
            self.assertEqual(X11SocketCatalog(root).listDisplays(), [":0", ":12"])


if __name__ == "__main__":
    unittest.main()
