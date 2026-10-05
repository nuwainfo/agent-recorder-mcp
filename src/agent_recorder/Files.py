#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import pathlib


logger = logging.getLogger(__name__)


class RecordingFile:
    HEAD_BYTES = 256 * 1024
    TAIL_BYTES = 4 * 1024 * 1024

    @staticmethod
    def isPlayable(path: pathlib.Path) -> bool:
        try:
            if not path.is_file():
                return False

            size = path.stat().st_size
            if size < 16:
                return False

            with path.open("rb") as handle:
                head = handle.read(RecordingFile.HEAD_BYTES)
                tail = b""
                if size > len(head):
                    handle.seek(max(0, size - RecordingFile.TAIL_BYTES))
                    tail = handle.read(RecordingFile.TAIL_BYTES)
        except FileNotFoundError:
            return False

        blob = head + tail
        return b"ftyp" in blob and b"moov" in blob

    @staticmethod
    def deleteMedia(recording) -> None:
        try:
            recording.outputPath.unlink(missing_ok=True)
        except OSError as error:
            logger.error("Could not delete recording %s: %s", recording.outputPath, error)
            raise

    @staticmethod
    def deleteLog(recording) -> None:
        try:
            recording.logPath.unlink(missing_ok=True)
        except OSError as error:
            logger.debug("Could not delete recording log %s: %s", recording.logPath, error)
