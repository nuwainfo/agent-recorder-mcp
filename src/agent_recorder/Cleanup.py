#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from agent_recorder.Files import RecordingFile
from agent_recorder.Models import RecordingState


logger = logging.getLogger(__name__)


class AfterDownloadCleanup:
    """Delete the local file after FFL reports that the transfer completed."""

    def watch(self, recording, session, store, hook) -> None:
        def onCompleted() -> None:
            self._complete(recording, session, store, hook)

        hook.onComplete(onCompleted)

    def _complete(self, recording, session, store, hook) -> None:
        if recording.state != RecordingState.SHARED:
            logger.info(
                "Ignoring transfer completion for %s in state %s",
                recording.recordingId,
                recording.state.name.lower(),
            )
            return

        try:
            session.stop()
        except Exception as error:
            logger.warning(
                "Could not stop the share session for %s: %s",
                recording.recordingId,
                error,
            )

        RecordingFile.deleteMedia(recording)
        RecordingFile.deleteLog(recording)
        recording.state = RecordingState.CLEANED
        recording.shareSession = None
        recording.completionHook = None
        store.save(recording)
        try:
            hook.close()
        except Exception as error:
            logger.warning(
                "Could not close the transfer hook for %s: %s",
                recording.recordingId,
                error,
            )

        logger.info("Deleted local recording %s after download", recording.recordingId)
