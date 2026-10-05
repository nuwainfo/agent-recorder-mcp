# AGENTS.md

`agent-recorder-mcp` records the agent computer display and returns a replay link. FastFileLink delivers the file. The video is not sent to the model.

## Layout

- `src/agent_recorder/MCP.py` — MCP tools only.
- `src/agent_recorder/Service.py` — one-recording lifecycle and orphan recovery.
- `src/agent_recorder/Display.py` — X11 display selection for this agent process tree.
- `src/agent_recorder/Capture.py` — FFmpeg command and process lifetime.
- `src/agent_recorder/Delivery.py` — FFL and local delivery.
- `src/agent_recorder/Cleanup.py` — delete after the FFL download event.
- `src/agent_recorder/Store.py` — snake_case JSON metadata on disk.
- `.grok/skills/agent-session-recording/SKILL.md` — when the agent must record.

## Rules

Follow the FastFileLink clean-code rules: camelCase in Python and tool payloads, snake_case only in on-disk JSON, `IntEnum` members inside the process, early returns, no silent fallbacks, no bare `except: pass`. Do not use `_` as a throwaway name.

Do not add a second capture backend, a dashboard, or cloud upload in this version. `after_upload` stays a rejected policy until a real upload path exists.

Display selection must fail with `No active agent display could be identified.` when this agent tree has no display. Do not substitute another socket.

## Commands

GrokBot installs from a checkout with uvx. The client command stays `uvx`.

```bash
uvx --from /path/to/agent-recorder-mcp install --target grok-build
uvx --from /path/to/agent-recorder-mcp install --print --target grok-build
```

`--print` does not write config and does not copy the skill. The registered server command is `uvx --from <that checkout> agent-recorder-mcp`. A git URL in `--from` is recorded as the later launch spec. A directory install is recorded as that directory because the package is not on PyPI.

Tests on this machine use the `recoding-mcp` conda environment:

```powershell
conda activate recoding-mcp
pip install -e .
python -m unittest discover -s tests -p "*Test.py" -v
```

The default suite does not open a network share. Use `tests/Smoke.py` on the Linux agent computer for a real capture.
