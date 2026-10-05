#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

"""Dispatch agent-recorder-mcp to the MCP server or to install/uninstall."""

from __future__ import annotations

import os
import sys

from importlib.metadata import version

from agent_recorder.InstallSource import DirectoryInstallSource
from agent_recorder.Paths import AppPaths
from agent_recorder.SkillInstall import SkillInstaller


os.environ.setdefault("FASTMCP_SHOW_CLI_BANNER", "false")


def _installSkillFromArgs() -> None:
    SkillInstaller().install(overwrite="--overwrite" in sys.argv)


def _dispatchInstall(command: str) -> None:
    binaryPath = os.environ.get("PYAPP")
    if binaryPath and binaryPath != "1" and os.path.isfile(binaryPath):
        os.environ["AGENT_RECORDER_BINARY"] = binaryPath

    if "--app-config" not in sys.argv:
        sys.argv.extend(["--app-config", str(AppPaths.installConfig())])

    if not os.environ.get("AGENT_RECORDER_BINARY"):
        spec = DirectoryInstallSource().directorySpec()
        sys.argv[:] = DirectoryInstallSource.appendSpec(sys.argv, spec)

    from mcp_install.Install import main as installMain

    uninstall = command == "uninstall" or "--uninstall" in sys.argv
    preview = "--print" in sys.argv
    if command == "uninstall" and "--uninstall" not in sys.argv:
        sys.argv.append("--uninstall")

    try:
        installMain()
    except SystemExit as exit:
        if not preview and not uninstall and exit.code in (0, None):
            _installSkillFromArgs()

        raise

    if not preview and not uninstall:
        _installSkillFromArgs()


def installCommand() -> None:
    """Console script used by `uvx --from <checkout> install`."""
    _dispatchInstall("install")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        print(version("agent-recorder-mcp"))
        return

    if len(sys.argv) > 1 and sys.argv[1] in {"install", "uninstall"}:
        command = sys.argv.pop(1)
        _dispatchInstall(command)
        return

    from agent_recorder.MCP import main as mcpMain

    mcpMain()


if __name__ == "__main__":
    main()
