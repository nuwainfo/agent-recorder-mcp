#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import ffl

from agent_recorder.Models import DeliveryError, DeliveryKind


class DeliveryResult:
    def __init__(self, url: str, session):
        self.url = url
        self.session = session


class FFLDelivery:
    """Share a finished recording through the ffl-python binding.

    The returned link is a live peer-to-peer source. Creating it does not
    mean the local file can be deleted.
    """

    def __init__(self, shareFunction=None):
        self._shareFunction = ffl.share if shareFunction is None else shareFunction

    def deliver(self, recording) -> DeliveryResult:
        session = self._shareFunction(
            str(recording.outputPath),
            name=recording.outputPath.name,
            capture_hook_events=True,
        )
        url = session.link
        if not isinstance(url, str) or not url:
            raise DeliveryError("FFL did not return a replay URL.")

        return DeliveryResult(url=url, session=session)


class LocalDelivery:
    """Return the local file URI and leave the file in place."""

    def deliver(self, recording) -> DeliveryResult:
        return DeliveryResult(url=recording.outputPath.resolve().as_uri(), session=None)


class DeliveryFactory:
    def __init__(self, implementations: dict):
        self._implementations = implementations

    def forKind(self, kind: DeliveryKind):
        delivery = self._implementations.get(kind)
        if delivery is None:
            raise DeliveryError(f"Delivery '{kind.name.lower()}' is not available.")

        return delivery
