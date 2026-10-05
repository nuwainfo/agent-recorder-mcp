#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path

from agent_recorder.Paths import AppPaths
from agent_recorder.SkillInstall import SkillInstaller


class SkillInstallTest(unittest.TestCase):

    def testProjectFilesResolve(self):
        self.assertTrue(AppPaths.installConfig().is_file())
        text = AppPaths.skillSource().read_text(encoding="utf-8")
        self.assertIn("startRecording", text)
        self.assertIn("finishRecording", text)

    def testInstallCopiesOnceUnlessOverwriteIsSet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "SKILL.md"
            source.write_text("original", encoding="utf-8")
            installer = SkillInstaller(source, root / "grok")
            destination = installer.install()
            self.assertEqual(destination.read_text(encoding="utf-8"), "original")
            source.write_text("changed", encoding="utf-8")
            installer.install()
            self.assertEqual(destination.read_text(encoding="utf-8"), "original")
            installer.install(overwrite=True)
            self.assertEqual(destination.read_text(encoding="utf-8"), "changed")


if __name__ == "__main__":
    unittest.main()
