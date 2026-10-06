# AGENTS.md

`agent-recorder-mcp` records the agent computer display and returns a replay link. FastFileLink delivers the file. The video is not sent to the model.

## Layout

- `src/agent_recorder/MCP.py` — MCP tools only.
- `src/agent_recorder/Service.py` — one-recording lifecycle and orphan recovery.
- `src/agent_recorder/Display.py` — X11 display selection for this agent process tree.
- `src/agent_recorder/Capture.py` — FFmpeg command and process lifetime.
- `src/agent_recorder/Delivery.py` — transfer strategies: FFL, local file, Google Drive handoff.
- `src/agent_recorder/Cleanup.py` — delete after FFL's `completed` event.
- `src/agent_recorder/Store.py` — snake_case JSON metadata on disk.
- `.grok/skills/agent-session-recording/SKILL.md` — when the agent must record.

## Rules

Follow the FastFileLink clean-code rules: camelCase in Python and tool payloads, snake_case only in on-disk JSON, `IntEnum` members inside the process, early returns, no silent fallbacks, no bare `except: pass`. Do not use `_` as a throwaway name.

Do not add a second capture backend or a dashboard. Google Drive is a transfer strategy: this process does not call Google. The assistant passes `outputDir` on `startRecording` as a folder its Drive tool can read, uploads `localPath`, then calls `confirmUpload`. `after_upload` is valid only for `google_drive`. A caller-supplied `outputDir` must already exist and be writable. The metadata `output_path` is that file, and cleanup deletes it.

Display selection must fail with `No active agent display could be identified.` when this agent tree has no display. Do not substitute another socket.

`after_download` uses ffl-python `session.on('completed')`. That event is `/transfer/complete`, which FFL emits once when an HTTP, WebRTC, or direct P2P transfer finishes. The handler stops the share and deletes the local file.

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
