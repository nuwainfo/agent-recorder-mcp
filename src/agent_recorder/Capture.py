#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import pathlib
import shutil
import signal
import subprocess
import sys
import time

from agent_recorder.Display import FrameStats, FrameView, X11Display
from agent_recorder.Models import CaptureError, FfmpegNotFoundError


logger = logging.getLogger(__name__)


class FfmpegLocator:
    def __init__(self, configuredPath: str | None = None):
        self._configuredPath = configuredPath

    def resolve(self) -> str:
        if self._configuredPath:
            path = pathlib.Path(self._configuredPath)
            if not path.is_file():
                raise FfmpegNotFoundError()

            return str(path)

        found = shutil.which("ffmpeg")
        if not found:
            raise FfmpegNotFoundError()

        return found


class OutputSize:
    MAX_WIDTH = 1280
    MAX_HEIGHT = 800

    @staticmethod
    def even(value: int) -> int:
        if value < 2:
            return 2

        if value % 2:
            return value - 1

        return value

    @classmethod
    def fit(
        cls,
        width: int,
        height: int,
        maxWidth: int | None = None,
        maxHeight: int | None = None,
    ) -> tuple[int, int]:
        limitWidth = cls.MAX_WIDTH if maxWidth is None else maxWidth
        limitHeight = cls.MAX_HEIGHT if maxHeight is None else maxHeight
        if width <= limitWidth and height <= limitHeight:
            return cls.even(width), cls.even(height)

        if width * limitHeight >= height * limitWidth:
            fittedWidth = limitWidth
            fittedHeight = height * limitWidth // width
        else:
            fittedHeight = limitHeight
            fittedWidth = width * limitHeight // height

        return cls.even(fittedWidth), cls.even(fittedHeight)


class X11Geometry:
    def sizeOf(self, display: str) -> tuple[int, int]:
        size = self._fromXdpyinfo(display)
        if size is not None:
            return size

        size = self._fromXwininfo(display)
        if size is not None:
            return size

        raise CaptureError(f"Could not read the size of display {display}.")

    def _fromXdpyinfo(self, display: str) -> tuple[int, int] | None:
        binary = shutil.which("xdpyinfo")
        if binary is None:
            logger.debug("xdpyinfo is not installed")
            return None

        completed = self._run([binary, "-display", display])
        if completed is None or completed.returncode != 0:
            return None

        return self._parseDimensions(completed.stdout)

    def _fromXwininfo(self, display: str) -> tuple[int, int] | None:
        binary = shutil.which("xwininfo")
        if binary is None:
            logger.debug("xwininfo is not installed")
            return None

        completed = self._run([binary, "-root", "-display", display])
        if completed is None or completed.returncode != 0:
            return None

        return self._parseXwininfo(completed.stdout)

    @staticmethod
    def _run(command: list[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                text=True,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            logger.debug("Display size command failed: %s", error)
            return None

    @staticmethod
    def _parseDimensions(text: str) -> tuple[int, int] | None:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("dimensions:"):
                continue

            parts = stripped.split()
            if len(parts) < 2 or "x" not in parts[1]:
                continue

            widthText, heightText = parts[1].split("x", 1)
            return int(widthText), int(heightText)

        return None

    @staticmethod
    def _parseXwininfo(text: str) -> tuple[int, int] | None:
        width = None
        height = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("Width:"):
                width = int(stripped.split(":", 1)[1].strip())
            elif stripped.startswith("Height:"):
                height = int(stripped.split(":", 1)[1].strip())

        if width is None or height is None:
            return None

        return width, height


class FfmpegProcess:
    def __init__(self, process: subprocess.Popen, logPath: pathlib.Path, logHandle):
        self._process = process
        self._logPath = logPath
        self._logHandle = logHandle
        self.pid = process.pid

    @property
    def running(self) -> bool:
        return self._process.poll() is None

    @property
    def returnCode(self) -> int | None:
        return self._process.returncode

    def wait(self, timeout: float | None = None) -> int:
        return self._process.wait(timeout=timeout)

    def confirmStarted(self, graceSeconds: float) -> bool:
        deadline = time.time() + graceSeconds
        while time.time() < deadline:
            if self._process.poll() is not None:
                self._closeLog()
                return False

            time.sleep(0.05)

        return True

    def stop(self, timeout: float) -> None:
        if self._process.poll() is None:
            self._signalQuit()
            try:
                self._process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.warning("FFmpeg did not exit after interrupt; terminating pid %s", self.pid)
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    logger.warning("FFmpeg did not exit after terminate; killing pid %s", self.pid)
                    self._process.kill()
                    self._process.wait(timeout=3)

        self._closeLog()

    def stderrText(self) -> str:
        self._closeLog()
        try:
            return self._logPath.read_text(encoding="utf-8", errors="replace")[-4000:]
        except OSError as error:
            logger.debug("Could not read ffmpeg log %s: %s", self._logPath, error)
            return ""

    def _signalQuit(self) -> None:
        self._process.send_signal(signal.SIGINT)

    def _closeLog(self) -> None:
        handle = self._logHandle
        if handle is None:
            return

        self._logHandle = None
        try:
            handle.close()
        except OSError as error:
            logger.debug("Could not close ffmpeg log: %s", error)


class X11GrabCapture:
    """Record an X11 display to an H.264 MP4 file."""

    STARTUP_GRACE_SECONDS = 0.4
    STOP_TIMEOUT_SECONDS = 15

    def __init__(self, locator: FfmpegLocator | None = None, geometry: X11Geometry | None = None):
        self._locator = locator if locator is not None else FfmpegLocator()
        self._geometry = geometry if geometry is not None else X11Geometry()

    @staticmethod
    def buildCommand(
        ffmpeg: str,
        display: str,
        outputPath: pathlib.Path,
        fps: int,
        maxDurationSeconds: int,
        nativeSize: tuple[int, int],
        outputSize: tuple[int, int],
    ) -> list[str]:
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-f", "x11grab",
            "-draw_mouse", "1",
            "-framerate", str(fps),
            "-video_size", f"{nativeSize[0]}x{nativeSize[1]}",
            "-i", X11Display.grabTarget(display),
        ]
        if outputSize != nativeSize:
            command.extend(["-vf", f"scale={outputSize[0]}:{outputSize[1]}"])

        command.extend([
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-crf", "32",
            "-g", str(max(fps * 2, 2)),
            "-t", str(maxDurationSeconds),
            "-movflags", "+faststart",
            str(outputPath),
        ])
        return command

    def ensureAvailable(self) -> str:
        return self._locator.resolve()

    def start(self, recording) -> FfmpegProcess:
        if sys.platform != "linux":
            raise CaptureError(
                "Screen capture in this version supports the agent Linux X11 display only."
            )

        ffmpeg = self.ensureAvailable()
        nativeSize = self._geometry.sizeOf(recording.display)
        outputSize = OutputSize.fit(nativeSize[0], nativeSize[1])
        command = self.buildCommand(
            ffmpeg,
            recording.display,
            recording.outputPath,
            recording.fps,
            recording.maxDurationSeconds,
            nativeSize,
            outputSize,
        )
        recording.outputPath.parent.mkdir(parents=True, exist_ok=True)
        logHandle = recording.logPath.open("wb")
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=logHandle,
                start_new_session=True,
            )
        except OSError as error:
            logHandle.close()
            raise CaptureError(str(error)) from error

        handle = FfmpegProcess(process, recording.logPath, logHandle)
        if not handle.confirmStarted(self.STARTUP_GRACE_SECONDS):
            detail = handle.stderrText() or "FFmpeg exited immediately."
            raise CaptureError(detail)

        return handle

    def stop(self, handle: FfmpegProcess) -> None:
        handle.stop(self.STOP_TIMEOUT_SECONDS)


class FfmpegFrameProbe:
    """Grab one small frame so display selection can reject an unreadable screen."""

    def __init__(self, locator: FfmpegLocator):
        self._locator = locator

    def probe(self, display: str) -> FrameView:
        if sys.platform != "linux":
            raise CaptureError(
                "Screen capture in this version supports the agent Linux X11 display only."
            )

        ffmpeg = self._locator.resolve()
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-f", "x11grab",
            "-framerate", "1",
            "-video_size", "64x64",
            "-i", X11Display.grabTarget(display),
            "-frames:v", "1",
            "-f", "rawvideo",
            "-pix_fmt", "gray",
            "pipe:1",
        ]
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            logger.warning("Could not grab a frame from %s: %s", display, error)
            return FrameView(False, True)

        if completed.returncode != 0 or len(completed.stdout) < 64:
            logger.warning(
                "Frame grab failed for %s: %s",
                display,
                completed.stderr.decode("utf-8", "replace")[:500],
            )
            return FrameView(False, True)

        return FrameView(True, FrameStats.isBlank(completed.stdout))
