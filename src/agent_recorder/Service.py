#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import os
import pathlib
import signal
import threading
import time
import uuid

from datetime import datetime

from agent_recorder.Capture import FfmpegFrameProbe, FfmpegLocator, X11GrabCapture
from agent_recorder.Cleanup import AfterDownloadCleanup
from agent_recorder.Delivery import DeliveryFactory, FFLDelivery, LocalDelivery
from agent_recorder.Display import AgentDisplayDiscovery, LinuxProcessTable, X11SocketCatalog
from agent_recorder.Files import RecordingFile
from agent_recorder.Models import (
    CleanupPolicy,
    DeliveryError,
    DeliveryKind,
    RecorderError,
    Recording,
    RecordingNotFoundError,
    RecordingRequest,
    RecordingState,
)
from agent_recorder.Store import RecordingStore


logger = logging.getLogger(__name__)

ACTIVE_STATES = (
    RecordingState.RECORDING,
    RecordingState.FINALIZING,
    RecordingState.READY,
    RecordingState.SHARING,
)


class RecorderConfig:
    def __init__(self, rootDir: pathlib.Path, ffmpegPath: str | None):
        self.rootDir = rootDir
        self.ffmpegPath = ffmpegPath

    @property
    def recordingsDir(self) -> pathlib.Path:
        return self.rootDir / "recordings"

    @classmethod
    def fromEnvironment(cls) -> "RecorderConfig":
        configured = os.environ.get("AGENT_RECORDER_DIR")
        if configured:
            rootDir = pathlib.Path(configured).expanduser()
        else:
            rootDir = pathlib.Path.home() / ".agent-recorder"

        return cls(rootDir, os.environ.get("AGENT_RECORDER_FFMPEG") or None)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now().astimezone()


class HostProcessInspector:
    def isAlive(self, pid: int) -> bool:
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            return False

        try:
            os.kill(pid, 0)
        except OSError:
            return False

        return True

    def interrupt(self, pid: int) -> None:
        os.kill(pid, signal.SIGINT)

    def waitUntilExit(self, pid: int, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.isAlive(pid):
                return True

            time.sleep(0.1)

        return not self.isAlive(pid)


class StartResult:
    def __init__(self, recording: Recording, alreadyRecording: bool):
        self.recording = recording
        self.alreadyRecording = alreadyRecording


class RecordingService:
    """Own one capture at a time: start, finish, abort, and orphan recovery."""

    def __init__(self, config, discovery, capture, deliveries, cleanup, store, clock, inspector):
        self._config = config
        self._discovery = discovery
        self._capture = capture
        self._deliveries = deliveries
        self._cleanup = cleanup
        self._store = store
        self._clock = clock
        self._inspector = inspector
        self._lock = threading.Lock()
        self._active = None
        self._byId: dict[str, Recording] = {}
        self._recover()

    def _ownerAlive(self, recording: Recording) -> bool:
        pid = recording.mcpPid
        if not pid or pid == os.getpid():
            return False

        return self._inspector.isAlive(pid)

    def _expired(self, recording: Recording) -> bool:
        elapsed = (self._clock.now() - recording.startedAt).total_seconds()
        return elapsed >= recording.maxDurationSeconds

    def _stopPid(self, pid: int, recordingId: str) -> None:
        logger.info("Stopping orphan ffmpeg pid %s for %s", pid, recordingId)
        try:
            self._inspector.interrupt(pid)
        except OSError as error:
            logger.warning("Could not stop orphan ffmpeg %s: %s", pid, error)

        self._inspector.waitUntilExit(pid, 15)

    def _recoverCapture(self, recording: Recording) -> None:
        pid = recording.ffmpegPid
        wasAlive = bool(pid) and self._inspector.isAlive(pid)
        expired = self._expired(recording)
        if wasAlive and self._ownerAlive(recording) and not expired:
            return

        if wasAlive and pid is not None:
            self._stopPid(pid, recording.recordingId)

        if expired and RecordingFile.isPlayable(recording.outputPath):
            recording.state = RecordingState.READY
            recording.error = None
        else:
            recording.state = RecordingState.FAILED
            if wasAlive and not expired:
                recording.error = "FFmpeg was stopped because the recorder that owned it is gone."
            elif expired:
                recording.error = "FFmpeg reached its time limit but the file is not playable."
            else:
                recording.error = "FFmpeg exited before the recording was finished."

        recording.ffmpegPid = None
        self._store.save(recording)

    def _recoverInterruptedShare(self, recording: Recording) -> None:
        if RecordingFile.isPlayable(recording.outputPath):
            recording.state = RecordingState.READY
            recording.url = None
            recording.error = (
                "The share session ended before cleanup. Call finishRecording to share the file again."
            )
        else:
            recording.state = RecordingState.FAILED
            recording.error = "The recording file is not playable."

        self._store.save(recording)

    def _refuseForeignOwner(self, recording: Recording) -> None:
        if self._ownerAlive(recording):
            raise RecorderError(
                f"Recording {recording.recordingId} is owned by another live recorder."
            )

    def _recover(self) -> None:
        for recording in self._store.loadAll():
            if recording.state in (RecordingState.RECORDING, RecordingState.FINALIZING):
                if self._ownerAlive(recording) and not self._expired(recording):
                    continue

                self._recoverCapture(recording)
            elif recording.state in (RecordingState.SHARING, RecordingState.SHARED):
                if self._ownerAlive(recording):
                    continue

                self._recoverInterruptedShare(recording)
            else:
                continue

            self._byId[recording.recordingId] = recording

    def _activeRecording(self) -> Recording | None:
        recording = self._active
        if recording is None:
            return None

        if recording.state in ACTIVE_STATES:
            return recording

        return None

    def _find(self, recordingId: str) -> Recording:
        recording = self._byId.get(recordingId)
        if recording is not None:
            return recording

        recording = self._store.load(recordingId)
        if recording is None:
            raise RecordingNotFoundError(f"Recording was not found: {recordingId}")

        self._byId[recordingId] = recording
        return recording

    def _resolve(self, recordingId: str | None) -> Recording:
        if recordingId:
            return self._find(recordingId)

        recording = self._activeRecording()
        if recording is None:
            raise RecordingNotFoundError("There is no active recording.")

        return recording

    @staticmethod
    def _validateFinish(delivery: DeliveryKind, cleanup: CleanupPolicy) -> None:
        if cleanup == CleanupPolicy.AFTER_UPLOAD:
            raise DeliveryError("after_upload is not available in this version.")

        if cleanup == CleanupPolicy.AFTER_DOWNLOAD and delivery != DeliveryKind.FFL:
            raise DeliveryError("after_download cleanup requires ffl delivery.")

    @staticmethod
    def _newId(startedAt: datetime) -> str:
        stamp = startedAt.strftime("%Y%m%d_%H%M%S")
        suffix = uuid.uuid4().hex[:6]
        return f"rec_{stamp}_{suffix}"

    def _create(self, display: str, fps: int, maxDurationSeconds: int) -> Recording:
        startedAt = self._clock.now()
        recordingId = self._newId(startedAt)
        directory = self._config.recordingsDir
        directory.mkdir(parents=True, exist_ok=True)
        return Recording(
            recordingId=recordingId,
            state=RecordingState.RECORDING,
            display=display,
            fps=fps,
            startedAt=startedAt,
            maxDurationSeconds=maxDurationSeconds,
            outputPath=directory / f"{recordingId}.mp4",
            logPath=directory / f"{recordingId}.log",
            ffmpegPid=None,
            mcpPid=os.getpid(),
            cleanup=None,
            delivery=None,
            url=None,
            error=None,
        )

    def _applyFailure(self, recording: Recording, message: str) -> None:
        recording.state = RecordingState.FAILED
        recording.error = message
        recording.handle = None
        recording.ffmpegPid = None
        if self._active is recording:
            self._active = None

        self._store.save(recording)

    def _markFailed(self, recording: Recording, message: str) -> None:
        with self._lock:
            self._applyFailure(recording, message)

    def _onCaptureExit(self, recording: Recording, handle) -> None:
        try:
            handle.wait()
        except Exception as error:
            logger.exception("Recording watcher failed for %s", recording.recordingId)
            self._markFailed(recording, str(error))
            return

        with self._lock:
            if recording.state != RecordingState.RECORDING:
                return

            if handle.returnCode == 0 and RecordingFile.isPlayable(recording.outputPath):
                recording.state = RecordingState.READY
                recording.error = None
                recording.ffmpegPid = None
                recording.handle = None
                self._store.save(recording)
                return

            detail = handle.stderrText().strip()
            self._applyFailure(recording, detail or "FFmpeg exited before the recording was finished.")

    def _watch(self, recording: Recording, handle) -> None:
        thread = threading.Thread(
            target=self._onCaptureExit,
            args=(recording, handle),
            name=f"agent-recorder-{recording.recordingId}",
            daemon=True,
        )
        recording.watchThread = thread
        thread.start()

    def _stopHandle(self, recording: Recording, handle) -> None:
        if handle is None:
            return

        try:
            self._capture.stop(handle)
        except Exception as error:
            logger.exception("Could not stop ffmpeg for %s", recording.recordingId)
            self._markFailed(recording, str(error))
            raise

    def _stopHandleQuiet(self, recording: Recording, handle) -> None:
        if handle is None:
            return

        try:
            self._capture.stop(handle)
        except Exception as error:
            logger.warning("Could not stop ffmpeg for %s: %s", recording.recordingId, error)

    def _stopCaptureProcess(self, recording: Recording, handle) -> None:
        if handle is not None:
            self._stopHandleQuiet(recording, handle)
            return

        if recording.ffmpegPid and self._inspector.isAlive(recording.ffmpegPid):
            self._stopPid(recording.ffmpegPid, recording.recordingId)

    def _stopShareQuiet(self, recording: Recording) -> None:
        session = recording.shareSession
        if session is None:
            return

        try:
            session.stop()
        except Exception as error:
            logger.warning("Could not stop the share for %s: %s", recording.recordingId, error)

    def _ensurePlayable(self, recording: Recording) -> None:
        if RecordingFile.isPlayable(recording.outputPath):
            with self._lock:
                recording.state = RecordingState.READY
                recording.handle = None
                recording.ffmpegPid = None
                self._store.save(recording)
            return

        detail = ""
        if recording.handle is not None:
            detail = recording.handle.stderrText().strip()

        message = detail or "Recording file is incomplete and cannot be shared."
        self._markFailed(recording, message)
        raise RecorderError(message)

    def start(
        self,
        fps: int = RecordingRequest.DEFAULT_FPS,
        maxDurationSeconds: int = RecordingRequest.DEFAULT_MAX_DURATION_SECONDS,
    ) -> StartResult:
        fps = RecordingRequest.fps(fps)
        maxDurationSeconds = RecordingRequest.maxDuration(maxDurationSeconds)
        with self._lock:
            active = self._activeRecording()
            if active is not None:
                return StartResult(active, True)

            self._capture.ensureAvailable()
            display = self._discovery.identify()
            recording = self._create(display, fps, maxDurationSeconds)
            try:
                handle = self._capture.start(recording)
            except Exception:
                RecordingFile.deleteMedia(recording)
                RecordingFile.deleteLog(recording)
                raise

            recording.handle = handle
            recording.ffmpegPid = handle.pid
            self._byId[recording.recordingId] = recording
            self._active = recording
            self._store.save(recording)
            self._watch(recording, handle)
            return StartResult(recording, False)

    def status(self, recordingId: str | None = None) -> Recording | None:
        with self._lock:
            if recordingId:
                return self._find(recordingId)

            return self._activeRecording()

    def finish(
        self,
        recordingId: str | None = None,
        delivery: DeliveryKind = DeliveryKind.FFL,
        cleanup: CleanupPolicy = CleanupPolicy.AFTER_DOWNLOAD,
    ) -> Recording:
        self._validateFinish(delivery, cleanup)
        handle = None
        with self._lock:
            recording = self._resolve(recordingId)
            self._refuseForeignOwner(recording)
            if recording.state in (RecordingState.SHARED, RecordingState.CLEANED) and recording.url:
                return recording

            if recording.state == RecordingState.READY:
                recording.delivery = delivery
                recording.cleanup = cleanup
            elif recording.state == RecordingState.RECORDING:
                recording.state = RecordingState.FINALIZING
                recording.delivery = delivery
                recording.cleanup = cleanup
                self._store.save(recording)
                handle = recording.handle
            else:
                raise RecorderError(
                    f"Recording {recording.recordingId} is {recording.state.name.lower()} and cannot be finished."
                )

        if recording.state == RecordingState.FINALIZING:
            self._stopHandle(recording, handle)
            self._ensurePlayable(recording)

        with self._lock:
            if recording.state == RecordingState.FAILED:
                raise RecorderError(recording.error or "Recording file is incomplete and cannot be shared.")

            recording.state = RecordingState.SHARING
            recording.delivery = delivery
            recording.cleanup = cleanup
            self._store.save(recording)

        try:
            result = self._deliveries.forKind(delivery).deliver(recording)
        except Exception as error:
            with self._lock:
                recording.state = RecordingState.READY
                recording.error = str(error)
                self._store.save(recording)
            raise

        with self._lock:
            recording.url = result.url
            recording.shareSession = result.session
            recording.error = None
            recording.state = RecordingState.SHARED
            if self._active is recording:
                self._active = None

            self._store.save(recording)

        if cleanup == CleanupPolicy.AFTER_DOWNLOAD:
            self._cleanup.watch(recording, result.session, self._store)

        return recording

    def abort(self, recordingId: str | None = None, deletePartial: bool = True) -> Recording:
        with self._lock:
            recording = self._resolve(recordingId)
            self._refuseForeignOwner(recording)
            if recording.state in (RecordingState.CLEANED, RecordingState.ABORTED):
                return recording

            handle = recording.handle
            recording.state = RecordingState.ABORTED
            if self._active is recording:
                self._active = None

            self._store.save(recording)

        self._stopCaptureProcess(recording, handle)
        self._stopShareQuiet(recording)
        if deletePartial:
            RecordingFile.deleteMedia(recording)
            RecordingFile.deleteLog(recording)

        with self._lock:
            recording.handle = None
            recording.ffmpegPid = None
            recording.shareSession = None
            self._store.save(recording)

        return recording

    def cleanup(self, recordingId: str) -> Recording:
        with self._lock:
            recording = self._find(recordingId)
            self._refuseForeignOwner(recording)
            handle = recording.handle
            recording.state = RecordingState.CLEANED
            if self._active is recording:
                self._active = None

            self._store.save(recording)

        self._stopCaptureProcess(recording, handle)
        self._stopShareQuiet(recording)
        RecordingFile.deleteMedia(recording)
        RecordingFile.deleteLog(recording)
        with self._lock:
            recording.state = RecordingState.CLEANED
            recording.handle = None
            recording.ffmpegPid = None
            recording.shareSession = None
            self._store.save(recording)

        return recording

    def payloadFor(self, recording: Recording, alreadyRecording: bool = False) -> dict:
        return recording.toPayload(self._clock.now(), alreadyRecording=alreadyRecording)


def buildDefaultService() -> RecordingService:
    config = RecorderConfig.fromEnvironment()
    locator = FfmpegLocator(config.ffmpegPath)
    return RecordingService(
        config=config,
        discovery=AgentDisplayDiscovery(
            LinuxProcessTable(),
            X11SocketCatalog(),
            FfmpegFrameProbe(locator),
        ),
        capture=X11GrabCapture(locator),
        deliveries=DeliveryFactory({
            DeliveryKind.FFL: FFLDelivery(),
            DeliveryKind.LOCAL: LocalDelivery(),
        }),
        cleanup=AfterDownloadCleanup(),
        store=RecordingStore(config.recordingsDir),
        clock=SystemClock(),
        inspector=HostProcessInspector(),
    )
