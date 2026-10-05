#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: Apache-2.0

"""Record the agent display for a few seconds and finish.

Run this on the Linux computer the agent is using. Watch the result and confirm
the browser is visible, the picture is not black, and it is not another agent's
desktop. This script does not open a browser itself.
"""

from __future__ import annotations

import argparse
import time

from agent_recorder.Models import CleanupPolicy, DeliveryKind
from agent_recorder.Service import buildDefaultService


def main() -> None:
    parser = argparse.ArgumentParser(description="Record the agent display and finish.")
    parser.add_argument("--seconds", type=int, default=3)
    parser.add_argument("--delivery", choices=["local", "ffl"], default="local")
    parser.add_argument("--cleanup", choices=["manual", "after_download"], default="manual")
    args = parser.parse_args()

    service = buildDefaultService()
    started = service.start()
    print(service.payloadFor(started.recording, alreadyRecording=started.alreadyRecording))
    time.sleep(args.seconds)
    finished = service.finish(
        started.recording.recordingId,
        DeliveryKind.parse(args.delivery),
        CleanupPolicy.parse(args.cleanup),
    )
    print(service.payloadFor(finished))


if __name__ == "__main__":
    main()
