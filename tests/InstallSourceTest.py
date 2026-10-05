#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

import json
import pathlib
import tempfile
import unittest

from agent_recorder.InstallSource import DirectoryInstallSource


class InstallSourceTest(unittest.TestCase):

    def testWindowsFileUrlDropsTheExtraSlash(self):
        path = DirectoryInstallSource.fileUrlPath("file:///C:/Users/Naga/agent-recorder-mcp")
        self.assertEqual(path, pathlib.Path("C:/Users/Naga/agent-recorder-mcp"))

    def testPosixFileUrlKeepsTheAbsolutePath(self):
        path = DirectoryInstallSource.fileUrlPath("file:///home/grokbot/agent-recorder-mcp")
        self.assertEqual(path, pathlib.Path("/home/grokbot/agent-recorder-mcp"))

    def testDirectorySpecUsesACheckoutAndIgnoresGit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
            url = root.resolve().as_uri()
            spec = DirectoryInstallSource(json.dumps({"url": url})).directorySpec()
            self.assertEqual(pathlib.Path(spec), root.resolve())

        gitSpec = DirectoryInstallSource(
            json.dumps({"url": "https://github.com/nuwainfo/agent-recorder-mcp.git", "vcs_info": {"vcs": "git"}})
        ).directorySpec()
        self.assertIsNone(gitSpec)

    def testMissingOrCorruptMetadata(self):
        self.assertIsNone(DirectoryInstallSource("").directorySpec())
        with self.assertRaises(ValueError):
            DirectoryInstallSource("{").directorySpec()

    def testAppendSpecOnce(self):
        argv = ["install", "--print"]
        spec = "C:/src/agent-recorder-mcp"
        once = DirectoryInstallSource.appendSpec(argv, spec)
        self.assertEqual(once, ["install", "--print", "--from", spec])
        self.assertEqual(DirectoryInstallSource.appendSpec(once, spec), once)
        self.assertEqual(argv, ["install", "--print"])

    def testInstalledCheckoutResolvesToThisRepo(self):
        spec = DirectoryInstallSource().directorySpec()
        self.assertIsNotNone(spec)
        repoRoot = pathlib.Path(__file__).resolve().parents[1]
        self.assertEqual(pathlib.Path(spec).resolve(), repoRoot)


if __name__ == "__main__":
    unittest.main()
