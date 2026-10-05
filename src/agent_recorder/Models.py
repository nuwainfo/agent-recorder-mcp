#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pathlib

from datetime import datetime
from enum import IntEnum


class RecorderError(Exception):
    """Base error for recording, delivery, and cleanup failures."""


class FfmpegNotFoundError(RecorderError):
    def __init__(self):
        super().__init__("FFmpeg is required but was not found.")


class DisplayNotFoundError(RecorderError):
    def __init__(self):
        super().__init__("No active agent display could be identified.")


class RecordingNotFoundError(RecorderError):
    pass


class DeliveryError(RecorderError):
    pass


class CaptureError(RecorderError):
    pass


class ApiEnum(IntEnum):
    @classmethod
    def parse(cls, value: str):
        if not isinstance(value, str):
            raise ValueError(f"Unknown value for {cls.__name__}")

        key = value.strip().upper()
        if key not in cls.__members__:
            known = ", ".join(name.lower() for name in cls.__members__)
            raise ValueError(f"Unknown value '{value}'. Expected one of: {known}")

        return cls[key]


class RecordingState(ApiEnum):
    RECORDING = 1
    FINALIZING = 2
    READY = 3
    SHARING = 4
    SHARED = 5
    FAILED = 6
    ABORTED = 7
    CLEANED = 8


class CleanupPolicy(ApiEnum):
    AFTER_DOWNLOAD = 1
    AFTER_UPLOAD = 2
    MANUAL = 3


class DeliveryKind(ApiEnum):
    FFL = 1
    LOCAL = 2
    GOOGLE_DRIVE = 3


class UploadStatus(ApiEnum):
    PENDING = 1
    CONFIRMED = 2


class RecordingRequest:
    DEFAULT_FPS = 5
    DEFAULT_MAX_DURATION_SECONDS = 7200
    MIN_FPS = 1
    MAX_FPS = 30
    MIN_DURATION_SECONDS = 1
    MAX_DURATION_SECONDS = 24 * 60 * 60

    @staticmethod
    def _integer(value: int, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")

    @staticmethod
    def fps(value: int) -> int:
        RecordingRequest._integer(value, "fps")
        if value < RecordingRequest.MIN_FPS or value > RecordingRequest.MAX_FPS:
            raise ValueError(
                f"fps must be between {RecordingRequest.MIN_FPS} and {RecordingRequest.MAX_FPS}"
            )

        return value

    @staticmethod
    def maxDuration(value: int) -> int:
        RecordingRequest._integer(value, "maxDurationSeconds")
        if (
            value < RecordingRequest.MIN_DURATION_SECONDS
            or value > RecordingRequest.MAX_DURATION_SECONDS
        ):
            raise ValueError(
                "maxDurationSeconds must be between "
                f"{RecordingRequest.MIN_DURATION_SECONDS} and {RecordingRequest.MAX_DURATION_SECONDS}"
            )

        return value


class Recording:
    """One local capture and the delivery state attached to it."""

    def __init__(
        self,
        recordingId: str,
        state: RecordingState,
        display: str,
        fps: int,
        startedAt: datetime,
        maxDurationSeconds: int,
        outputPath: pathlib.Path,
        logPath: pathlib.Path,
        ffmpegPid: int | None,
        mcpPid: int | None,
        cleanup: CleanupPolicy | None,
        delivery: DeliveryKind | None,
        url: str | None,
        error: str | None,
        uploadStatus: UploadStatus | None = None,
    ):
        self.recordingId = recordingId
        self.state = state
        self.display = display
        self.fps = fps
        self.startedAt = startedAt
        self.maxDurationSeconds = maxDurationSeconds
        self.outputPath = outputPath
        self.logPath = logPath
        self.ffmpegPid = ffmpegPid
        self.mcpPid = mcpPid
        self.cleanup = cleanup
        self.delivery = delivery
        self.url = url
        self.error = error
        self.uploadStatus = uploadStatus
        self.handle = None
        self.shareSession = None
        self.completionHook = None
        self.watchThread = None

    @staticmethod
    def idlePayload() -> dict[str, str]:
        return {"state": "idle"}

    @classmethod
    def fromDisk(cls, data: dict) -> "Recording":
        cleanup = data["cleanup"]
        delivery = data["delivery"]
        uploadStatus = data.get("upload_status")
        return cls(
            recordingId=data["recording_id"],
            state=RecordingState.parse(data["state"]),
            display=data["display"],
            fps=data["fps"],
            startedAt=datetime.fromisoformat(data["started_at"]),
            maxDurationSeconds=data["max_duration_seconds"],
            outputPath=pathlib.Path(data["output_path"]),
            logPath=pathlib.Path(data["log_path"]),
            ffmpegPid=data["ffmpeg_pid"],
            mcpPid=data["mcp_pid"],
            cleanup=None if cleanup is None else CleanupPolicy.parse(cleanup),
            delivery=None if delivery is None else DeliveryKind.parse(delivery),
            url=data["url"],
            error=data["error"],
            uploadStatus=None if uploadStatus is None else UploadStatus.parse(uploadStatus),
        )

    def startedAtText(self) -> str:
        return self.startedAt.isoformat(timespec="seconds")

    def durationSeconds(self, now: datetime) -> int:
        return max(0, int((now - self.startedAt).total_seconds()))

    def sizeBytes(self) -> int:
        try:
            if not self.outputPath.is_file():
                return 0

            return self.outputPath.stat().st_size
        except FileNotFoundError:
            return 0

    def toDisk(self) -> dict:
        return {
            "recording_id": self.recordingId,
            "state": self.state.name.lower(),
            "display": self.display,
            "fps": self.fps,
            "started_at": self.startedAtText(),
            "max_duration_seconds": self.maxDurationSeconds,
            "output_path": str(self.outputPath),
            "log_path": str(self.logPath),
            "ffmpeg_pid": self.ffmpegPid,
            "mcp_pid": self.mcpPid,
            "cleanup": None if self.cleanup is None else self.cleanup.name.lower(),
            "delivery": None if self.delivery is None else self.delivery.name.lower(),
            "url": self.url,
            "error": self.error,
            "upload_status": None if self.uploadStatus is None else self.uploadStatus.name.lower(),
        }

    def toPayload(self, now: datetime, alreadyRecording: bool = False) -> dict:
        payload = {
            "recordingId": self.recordingId,
            "state": self.state.name.lower(),
            "startedAt": self.startedAtText(),
            "display": self.display,
            "fps": self.fps,
            "durationSeconds": self.durationSeconds(now),
            "sizeBytes": self.sizeBytes(),
        }
        if self.url:
            payload["url"] = self.url

        if self.delivery is not None:
            payload["delivery"] = self.delivery.name.lower()

        if self.uploadStatus is not None:
            payload["uploadStatus"] = self.uploadStatus.name.lower()

        if self.delivery == DeliveryKind.GOOGLE_DRIVE and self.uploadStatus == UploadStatus.PENDING:
            payload["localPath"] = str(self.outputPath)

        if self.cleanup is not None:
            payload["cleanup"] = self.cleanup.name.lower()

        if self.error:
            payload["error"] = self.error

        if alreadyRecording:
            payload["alreadyRecording"] = True

        return payload
