#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

"""Resolve the uvx --from spec for a directory install."""

from __future__ import annotations

import importlib.metadata
import json
import os
import pathlib
import urllib.parse

from agent_recorder.Paths import AppPaths


class DirectoryInstallSource:
    """Local checkout that uv installed from a file URL.

    A git or PyPI install has no directory spec. mcp-install infers those.
    """

    def __init__(self, directUrlText: str | None = None):
        self._directUrlText = directUrlText

    @staticmethod
    def fileUrlPath(url: str) -> pathlib.Path:
        parsed = urllib.parse.urlparse(url)
        rawPath = urllib.parse.unquote(parsed.path)
        if os.name == "nt" and rawPath.startswith("/") and len(rawPath) >= 3 and rawPath[2] == ":":
            rawPath = rawPath[1:]

        return pathlib.Path(rawPath)

    @staticmethod
    def appendSpec(argv: list[str], spec: str | None) -> list[str]:
        if spec is None or "--from" in argv:
            return argv

        return [*argv, "--from", spec]

    def directorySpec(self) -> str | None:
        text = self._directUrlText
        if text is None:
            text = self._readInstalledDirectUrl()

        if text is None or text == "":
            return None

        try:
            info = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError("direct_url.json is not valid JSON") from error

        url = info.get("url")
        if not isinstance(url, str) or not url.startswith("file://"):
            return None

        projectPath = self.fileUrlPath(url)
        if not (projectPath / "pyproject.toml").is_file():
            return None

        return str(projectPath)

    def _readInstalledDirectUrl(self) -> str | None:
        try:
            distribution = importlib.metadata.distribution(self._distributionName())
        except importlib.metadata.PackageNotFoundError:
            return None

        return distribution.read_text("direct_url.json")

    @staticmethod
    def _distributionName() -> str:
        configPath = AppPaths.installConfig()
        data = json.loads(configPath.read_text(encoding="utf-8"))
        name = data.get("distributionName")
        if not isinstance(name, str) or name == "":
            raise ValueError(f"{configPath} is missing distributionName")

        return name
