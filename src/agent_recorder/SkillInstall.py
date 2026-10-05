#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import os
import pathlib

from agent_recorder.Paths import AppPaths


logger = logging.getLogger(__name__)


class SkillInstaller:
    """Copy the bundled agent skill into the user Grok skills directory."""

    def __init__(self, sourcePath: pathlib.Path | None = None, grokHome: pathlib.Path | None = None):
        self._sourcePath = sourcePath if sourcePath is not None else AppPaths.skillSource()
        self._grokHome = grokHome if grokHome is not None else self.defaultGrokHome()

    @staticmethod
    def defaultGrokHome() -> pathlib.Path:
        configured = os.environ.get("GROK_HOME")
        if configured:
            return pathlib.Path(configured).expanduser()

        return pathlib.Path.home() / ".grok"

    def destination(self) -> pathlib.Path:
        return self._grokHome / "skills" / AppPaths.SKILL_NAME / "SKILL.md"

    def install(self, overwrite: bool = False) -> pathlib.Path:
        source = self._sourcePath
        if not source.is_file():
            raise FileNotFoundError(f"Skill source was not found: {source}")

        destination = self.destination()
        if destination.is_file() and not overwrite:
            logger.info("Skill already installed at %s", destination)
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("Installed skill at %s", destination)
        return destination
