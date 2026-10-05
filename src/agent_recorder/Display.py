#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import os
import pathlib

from agent_recorder.Models import DisplayNotFoundError


logger = logging.getLogger(__name__)


class X11Display:
    """Normalize X11 display names and build an x11grab input."""

    @staticmethod
    def normalize(value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Display is empty")

        head, separator, screen = text.rpartition(".")
        if separator and screen.isdigit() and ":" in head:
            return head

        return text

    @staticmethod
    def grabTarget(display: str) -> str:
        return f"{X11Display.normalize(display)}.0"


class FrameView:
    def __init__(self, readable: bool, blank: bool):
        self.readable = readable
        self.blank = blank


class FrameStats:
    SAMPLE_LIMIT = 4096
    BLANK_MEAN_DEVIATION = 4.0

    @staticmethod
    def isBlank(samples: bytes, blankMeanDeviation: float | None = None) -> bool:
        length = len(samples)
        if length == 0:
            return True

        limit = blankMeanDeviation
        if limit is None:
            limit = FrameStats.BLANK_MEAN_DEVIATION

        step = max(1, length // FrameStats.SAMPLE_LIMIT)
        count = 0
        total = 0
        for index in range(0, length, step):
            total += samples[index]
            count += 1

        mean = total / count
        deviation = 0.0
        for index in range(0, length, step):
            deviation += abs(samples[index] - mean)

        return (deviation / count) < limit


class ProcessSnapshot:
    def __init__(
        self,
        pid: int,
        ppid: int,
        sid: int,
        name: str,
        command: str,
        display: str | None,
    ):
        self.pid = pid
        self.ppid = ppid
        self.sid = sid
        self.name = name
        self.command = command
        self.display = display


class LinuxProcessTable:
    """Read just enough of /proc to see DISPLAY on the agent process tree.

    Full environments are not kept. They can contain credentials.
    """

    def currentPid(self) -> int:
        return os.getpid()

    @staticmethod
    def parseStat(text: str) -> tuple[str, int, int]:
        openParen = text.find("(")
        closeParen = text.rfind(")")
        if openParen < 0 or closeParen < openParen:
            raise ValueError("Unrecognized process stat")

        name = text[openParen + 1:closeParen]
        fields = text[closeParen + 2:].split()
        if len(fields) < 4:
            raise ValueError("Unrecognized process stat")

        return name, int(fields[1]), int(fields[3])

    @staticmethod
    def displayFromEnviron(raw: bytes) -> str | None:
        for item in raw.split(b"\0"):
            if not item.startswith(b"DISPLAY="):
                continue

            value = item.split(b"=", 1)[1].decode("utf-8", "replace").strip()
            if value:
                return value

        return None

    def listProcesses(self) -> list[ProcessSnapshot]:
        proc = pathlib.Path("/proc")
        if not proc.is_dir():
            return []

        snapshots = []
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue

            snapshot = self._readProcess(int(entry.name), entry)
            if snapshot is not None:
                snapshots.append(snapshot)

        return snapshots

    def _readProcess(self, pid: int, base: pathlib.Path) -> ProcessSnapshot | None:
        try:
            statText = (base / "stat").read_text(encoding="utf-8", errors="replace")
            name, ppid, sid = self.parseStat(statText)
            command = self._command(base / "cmdline")
            display = self._display(base / "environ")
        except (OSError, ValueError) as error:
            logger.debug("Skipping process %s: %s", pid, error)
            return None

        return ProcessSnapshot(pid, ppid, sid, name, command, display)

    @staticmethod
    def _command(path: pathlib.Path) -> str:
        raw = path.read_bytes()
        return raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()

    def _display(self, path: pathlib.Path) -> str | None:
        return self.displayFromEnviron(path.read_bytes())


class X11SocketCatalog:
    def __init__(self, socketDir: pathlib.Path | None = None):
        if socketDir is None:
            socketDir = pathlib.Path("/tmp/.X11-unix")

        self._socketDir = pathlib.Path(socketDir)

    def listDisplays(self) -> list[str]:
        if not self._socketDir.is_dir():
            return []

        displays = []
        for entry in sorted(self._socketDir.iterdir(), key=lambda item: item.name):
            name = entry.name
            if not name.startswith("X"):
                continue

            number = name[1:]
            if not number.isdigit():
                continue

            displays.append(f":{number}")

        return displays


class AgentDisplayDiscovery:
    """Choose the display this agent process tree is actually using.

    A readable display outside that tree is never a fallback. Recording it
    would capture another session.
    """

    STOP_NAMES = frozenset(("systemd", "init", "sshd", "login", "cron"))
    MAX_ANCESTORS = 6
    BROWSER_TOKENS = ("chrome", "chromium", "firefox", "playwright", "msedge")

    def __init__(self, processTable, catalog, probe):
        self._processTable = processTable
        self._catalog = catalog
        self._probe = probe

    def _normalizedDisplay(self, process: ProcessSnapshot) -> str | None:
        if not process.display:
            return None

        try:
            return X11Display.normalize(process.display)
        except ValueError as error:
            logger.debug("Ignoring display %r from pid %s: %s", process.display, process.pid, error)
            return None

    def _isBrowser(self, process: ProcessSnapshot) -> bool:
        haystack = f"{process.name} {process.command}".lower()
        for token in self.BROWSER_TOKENS:
            if token in haystack:
                return True

        return False

    def _ancestorChain(self, current: ProcessSnapshot, byPid: dict[int, ProcessSnapshot]) -> list[ProcessSnapshot]:
        chain = [current]
        cursor = current
        while len(chain) < self.MAX_ANCESTORS:
            parent = byPid.get(cursor.ppid)
            if parent is None or parent.pid <= 1 or parent.name in self.STOP_NAMES:
                break

            chain.append(parent)
            cursor = parent

        return chain

    def _descendants(self, rootPid: int, snapshots: list[ProcessSnapshot]) -> set[int]:
        children: dict[int, list[int]] = {}
        for item in snapshots:
            children.setdefault(item.ppid, []).append(item.pid)

        related = set()
        stack = [rootPid]
        while stack:
            pid = stack.pop()
            if pid in related:
                continue

            related.add(pid)
            stack.extend(children.get(pid, []))

        return related

    def _matchingDisplays(
        self,
        pids: set[int],
        byPid: dict[int, ProcessSnapshot],
        candidates: set[str],
        browsersOnly: bool,
    ) -> set[str]:
        found = set()
        for pid in pids:
            process = byPid.get(pid)
            if process is None:
                continue

            if browsersOnly and not self._isBrowser(process):
                continue

            normalized = self._normalizedDisplay(process)
            if normalized is not None and normalized in candidates:
                found.add(normalized)

        return found

    def _nearestDisplay(self, chain: list[ProcessSnapshot], candidates: set[str]) -> str | None:
        for process in chain:
            normalized = self._normalizedDisplay(process)
            if normalized is not None and normalized in candidates:
                return normalized

        return None

    def _select(
        self,
        snapshots: list[ProcessSnapshot],
        currentPid: int,
        candidates: set[str],
    ) -> str | None:
        if not candidates:
            return None

        byPid = {item.pid: item for item in snapshots}
        current = byPid.get(currentPid)
        if current is None:
            return None

        chain = self._ancestorChain(current, byPid)
        related = self._descendants(chain[-1].pid, snapshots)
        browserDisplays = self._matchingDisplays(related, byPid, candidates, browsersOnly=True)
        if len(browserDisplays) > 1:
            logger.warning(
                "Browser processes in the agent tree use more than one display: %s",
                sorted(browserDisplays),
            )
            return None

        if len(browserDisplays) == 1:
            return next(iter(browserDisplays))

        return self._nearestDisplay(chain, candidates)

    def identify(self) -> str:
        candidates = set()
        for display in self._catalog.listDisplays():
            candidates.add(X11Display.normalize(display))

        chosen = self._select(
            self._processTable.listProcesses(),
            self._processTable.currentPid(),
            candidates,
        )
        if chosen is None:
            logger.warning(
                "No active agent display could be identified. candidates=%s",
                sorted(candidates),
            )
            raise DisplayNotFoundError()

        view = self._probe.probe(chosen)
        if not view.readable:
            logger.warning("Agent display %s could not be captured", chosen)
            raise DisplayNotFoundError()

        if view.blank:
            logger.info("Agent display %s is blank at startup", chosen)

        return chosen
