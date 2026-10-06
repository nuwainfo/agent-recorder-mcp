#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import ffl

from agent_recorder.Models import DeliveryError, DeliveryKind


class DeliveryResult:
    def __init__(self, url: str | None, session=None, awaitsUpload: bool = False):
        self.url = url
        self.session = session
        self.awaitsUpload = awaitsUpload


class DeliveryStrategy:
    """One way to hand a finished recording to the user."""

    def deliver(self, recording) -> DeliveryResult:
        raise NotImplementedError


class FFLDelivery(DeliveryStrategy):
    """Share a finished recording through ffl-python.

    The link is a live peer-to-peer source. The local file stays until
    ``session.on('completed')`` reports FFL's ``/transfer/complete`` event.
    """

    def __init__(self, shareFunction=None):
        self._shareFunction = ffl.share if shareFunction is None else shareFunction

    def deliver(self, recording) -> DeliveryResult:
        session = self._shareFunction(
            str(recording.outputPath),
            name=recording.outputPath.name,
        )
        url = getattr(session, "link", None)
        if not isinstance(url, str) or not url:
            self._close(session)
            raise DeliveryError("FFL did not return a replay URL.")

        return DeliveryResult(url=url, session=session)

    @staticmethod
    def _close(session) -> None:
        closer = getattr(session, "close", None)
        if not callable(closer):
            closer = getattr(session, "stop", None)

        if callable(closer):
            closer()


class LocalDelivery(DeliveryStrategy):
    """Return the local file URI and leave the file in place."""

    def deliver(self, recording) -> DeliveryResult:
        return DeliveryResult(url=recording.outputPath.resolve().as_uri(), session=None)


class GoogleDriveDelivery(DeliveryStrategy):
    """Hand the file to the assistant's connected Google Drive tool.

    This process does not call Google. finishRecording returns the local path,
    the assistant uploads it with the Drive connector, then confirmUpload
    stores the Drive link.
    """

    def deliver(self, recording) -> DeliveryResult:
        del recording
        return DeliveryResult(url=None, awaitsUpload=True)


class DeliveryFactory:
    def __init__(self, implementations: dict):
        self._implementations = implementations

    def forKind(self, kind: DeliveryKind) -> DeliveryStrategy:
        delivery = self._implementations.get(kind)
        if delivery is None:
            raise DeliveryError(f"Delivery '{kind.name.lower()}' is not available.")

        return delivery
