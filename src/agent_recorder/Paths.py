#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pathlib


class AppPaths:
    SKILL_NAME = "agent-session-recording"

    @staticmethod
    def _moduleDir() -> pathlib.Path:
        return pathlib.Path(__file__).resolve().parent

    @staticmethod
    def installConfig() -> pathlib.Path:
        here = AppPaths._moduleDir()
        candidates = (
            here.parents[1] / "install.config.json",
            here.parent / "install.config.json",
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate

        raise FileNotFoundError("install.config.json was not found")

    @staticmethod
    def skillSource() -> pathlib.Path:
        packaged = AppPaths._moduleDir() / "skills" / AppPaths.SKILL_NAME / "SKILL.md"
        if packaged.is_file():
            return packaged

        # Source checkout: src/agent_recorder/Paths.py -> repo/.grok/skills/...
        repoSkill = AppPaths._moduleDir().parents[1] / ".grok" / "skills" / AppPaths.SKILL_NAME / "SKILL.md"
        if repoSkill.is_file():
            return repoSkill

        raise FileNotFoundError("Agent session recording skill was not found")
