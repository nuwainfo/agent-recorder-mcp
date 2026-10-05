#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import logging
import pathlib

from agent_recorder.Models import Recording, RecordingNotFoundError


logger = logging.getLogger(__name__)


class RecordingStore:
    """Persist recording metadata as a user-visible JSON file.

    Keys on disk stay snake_case. Runtime objects stay camelCase.
    """

    def __init__(self, directory: pathlib.Path):
        self._directory = directory

    def _pathFor(self, recordingId: str) -> pathlib.Path:
        if not recordingId or "/" in recordingId or "\\" in recordingId or recordingId in {".", ".."}:
            raise RecordingNotFoundError(f"Recording was not found: {recordingId}")

        return self._directory / f"{recordingId}.json"

    def save(self, recording: Recording) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._pathFor(recording.recordingId)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(recording.toDisk(), indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    def load(self, recordingId: str) -> Recording | None:
        path = self._pathFor(recordingId)
        if not path.is_file():
            return None

        return self._read(path)

    def loadAll(self) -> list[Recording]:
        if not self._directory.is_dir():
            return []

        recordings = []
        for path in sorted(self._directory.glob("rec_*.json")):
            try:
                recordings.append(self._read(path))
            except (OSError, ValueError, KeyError, TypeError) as error:
                logger.error("Could not read recording metadata %s: %s", path, error)

        return recordings

    @staticmethod
    def _read(path: pathlib.Path) -> Recording:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Recording.fromDisk(data)
