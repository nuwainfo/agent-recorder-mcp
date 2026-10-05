#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading

from typing import Any

from fastmcp import FastMCP

from agent_recorder.Models import CleanupPolicy, DeliveryKind, Recording, RecordingRequest
from agent_recorder.Service import RecordingService, buildDefaultService


mcp = FastMCP("agent-recorder")


class ServiceHub:
    def __init__(self):
        self._service = None
        self._lock = threading.Lock()

    def current(self) -> RecordingService:
        with self._lock:
            if self._service is None:
                self._service = buildDefaultService()

            return self._service

    def use(self, service: RecordingService) -> None:
        with self._lock:
            self._service = service


hub = ServiceHub()


def _service() -> RecordingService:
    return hub.current()


@mcp.tool
def startRecording(
    fps: int = RecordingRequest.DEFAULT_FPS,
    maxDurationSeconds: int = RecordingRequest.DEFAULT_MAX_DURATION_SECONDS,
) -> dict[str, Any]:
    """Start recording the agent computer display before browser or computer-use actions.

    Call this before the first browser or computer action. The display is selected
    from this agent process tree. A display belonging to another session is not used.

    fps defaults to 5. maxDurationSeconds defaults to 7200. When the limit is reached
    the capture stops and the file is kept so finishRecording can still share it.

    If a recording is already active, or is waiting to be shared, that recording is
    returned and a second recorder is not started.
    """
    result = _service().start(fps=fps, maxDurationSeconds=maxDurationSeconds)
    return _service().payloadFor(result.recording, alreadyRecording=result.alreadyRecording)


@mcp.tool
def recordingStatus(recordingId: str | None = None) -> dict[str, Any]:
    """Return the recording state, duration, display, and file size.

    Omit recordingId to ask about the active recording. The state is idle when
    nothing is recording.
    """
    recording = _service().status(recordingId)
    if recording is None:
        return Recording.idlePayload()

    return _service().payloadFor(recording)


@mcp.tool
def finishRecording(
    recordingId: str | None = None,
    delivery: str = "ffl",
    cleanup: str = "after_download",
) -> dict[str, Any]:
    """Stop the recording, share it, and return a replay URL.

    delivery defaults to ffl, which shares the file through FastFileLink.
    cleanup defaults to after_download. The local file stays until the recipient
    finishes downloading, then the share stops and the file is deleted.
    after_upload is not available in this version. cleanup manual leaves the file
    on the agent computer.

    Put the returned url in the final answer as the operation replay. If this call
    fails, tell the user that no replay was produced and include the reason.
    """
    recording = _service().finish(
        recordingId,
        DeliveryKind.parse(delivery),
        CleanupPolicy.parse(cleanup),
    )
    return _service().payloadFor(recording)


@mcp.tool
def abortRecording(recordingId: str | None = None, deletePartial: bool = True) -> dict[str, Any]:
    """Stop a recording without sharing it.

    deletePartial defaults to true and removes the incomplete file. Use this when
    the task is cancelled or the capture is the wrong display.
    """
    recording = _service().abort(recordingId, deletePartial=deletePartial)
    return _service().payloadFor(recording)


@mcp.tool
def cleanupRecording(recordingId: str) -> dict[str, Any]:
    """Delete a local recording and stop any share still serving it.

    Pass the recordingId. This removes the file even if a recipient has not
    downloaded it yet.
    """
    recording = _service().cleanup(recordingId)
    return _service().payloadFor(recording)


def main() -> None:
    os.environ.setdefault("FASTMCP_SHOW_CLI_BANNER", "false")
    parser = argparse.ArgumentParser(prog="agent-recorder-mcp")
    parser.add_argument("--transport", choices=["stdio", "http", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--path", default="/mcp")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if args.transport == "stdio":
        mcp.run(show_banner=False)
        return

    mcp.run(
        transport=args.transport,
        host=args.host,
        port=args.port,
        path=args.path,
        show_banner=False,
    )


if __name__ == "__main__":
    main()
