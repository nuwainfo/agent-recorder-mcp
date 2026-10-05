# AGENTS.md

`agent-recorder-mcp` records the agent computer display and returns a replay link. FastFileLink delivers the file. The video is not sent to the model.

## Layout

- `src/agent_recorder/MCP.py` — MCP tools only.
- `src/agent_recorder/Service.py` — one-recording lifecycle and orphan recovery.
- `src/agent_recorder/Display.py` — X11 display selection for this agent process tree.
- `src/agent_recorder/Capture.py` — FFmpeg command and process lifetime.
- `src/agent_recorder/Delivery.py` — transfer strategies: FFL, local file, Google Drive handoff.
- `src/agent_recorder/CompletionHook.py` — local hook that accepts FFL completion events.
- `src/agent_recorder/Cleanup.py` — delete after the FFL download event.
- `src/agent_recorder/Store.py` — snake_case JSON metadata on disk.
- `.grok/skills/agent-session-recording/SKILL.md` — when the agent must record.

## Rules

Follow the FastFileLink clean-code rules: camelCase in Python and tool payloads, snake_case only in on-disk JSON, `IntEnum` members inside the process, early returns, no silent fallbacks, no bare `except: pass`. Do not use `_` as a throwaway name.

Do not add a second capture backend or a dashboard. Google Drive is a transfer strategy: this process does not call Google. The assistant uploads `localPath` with a connected Drive connector and then calls `confirmUpload`. `after_upload` is valid only for `google_drive`.

Display selection must fail with `No active agent display could be identified.` when this agent tree has no display. Do not substitute another socket.

FFL completion must be received on a hook that answers HTTP 200 and accepts `/download/complete` and `/webrtc/transfer/complete`. Do not wait on `ffl-python`'s semantic `completed` event. That channel answers 204 and maps `/hook/transfer/complete`, so a finished curl download never deletes the file or stops the share.

## Commands

People install the skill from tag `v0.1.0`. The skill installs the MCP connector and pins that same tag. Grok Bot adds a custom connector. `install --target grok-build` is only for Grok Build's `~/.grok/config.toml`.

```text
uvx --from git+https://github.com/nuwainfo/agent-recorder-mcp.git@v0.1.0 agent-recorder-mcp
```

Tests on this machine use the `recoding-mcp` conda environment:

```powershell
conda activate recoding-mcp
pip install -e .
python -m unittest discover -s tests -p "*Test.py" -v
```

The default suite does not open a network share. Use `tests/Smoke.py` on the Linux agent computer for a real capture.
