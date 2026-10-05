#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

"""Receive FFL transfer-completion events.

FFL's hook client stops delivering events after a non-200 response, and the
engine reports completion as /download/complete or /webrtc/transfer/complete.
"""

from __future__ import annotations

import json
import logging
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


logger = logging.getLogger(__name__)


class CompletionHook:
    COMPLETE_EVENTS = frozenset({
        "/download/complete",
        "/webrtc/transfer/complete",
    })

    def __init__(self):
        self._listeners = []
        self._done = False
        self._closed = False
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="agent-recorder-transfer-hook",
            daemon=True,
        )
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/events"

    @property
    def completed(self) -> bool:
        with self._lock:
            return self._done

    def onComplete(self, listener) -> None:
        with self._lock:
            if self._done:
                runNow = True
            else:
                self._listeners.append(listener)
                runNow = False

        if runNow:
            self._call(listener)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return

            self._closed = True

        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _handler(self):
        hook = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
                hook._accept(body)

            def log_message(self, formatString: str, *args) -> None:
                del formatString, args

        return Handler

    def _accept(self, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            logger.warning("Ignored a transfer hook payload that is not JSON: %s", error)
            return

        if not isinstance(payload, dict):
            logger.warning("Ignored a transfer hook payload that is not an object")
            return

        eventName = payload.get("event")
        if eventName not in self.COMPLETE_EVENTS:
            return

        self._schedule()

    def _schedule(self) -> None:
        with self._lock:
            if self._done:
                return

            self._done = True
            listeners = tuple(self._listeners)

        for listener in listeners:
            threading.Thread(
                target=self._call,
                args=(listener,),
                name="agent-recorder-transfer-complete",
                daemon=True,
            ).start()

    @staticmethod
    def _call(listener) -> None:
        try:
            listener()
        except Exception:
            logger.exception("Transfer completion listener failed")
