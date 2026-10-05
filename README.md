# agent-recorder-mcp

Local MCP server that records the computer an agent is using and returns a replay link when the task is done.

The recording stays on the agent machine. The model receives a link, not the video. FastFileLink is the delivery transport: the local file remains until the recipient finishes downloading.

This version targets the Linux X11 display used by GrokBot. It does not record the user's own desktop from another machine.

## Install

Give the assistant one URL. Install the skill from tag `v0.1.0` first. The skill then installs the MCP connector for whichever assistant is running, and it carries the rule that browser and computer-use work is recorded.

```bash
mkdir -p ~/.grok/skills/agent-session-recording
curl -fsSL \
  -o ~/.grok/skills/agent-session-recording/SKILL.md \
  https://raw.githubusercontent.com/nuwainfo/agent-recorder-mcp/v0.1.0/.grok/skills/agent-session-recording/SKILL.md
```

Claude uses `~/.claude/skills/agent-session-recording/SKILL.md`. The same file is the source for every assistant. `uv` selects Python 3.11 or newer when the skill installs the connector.

The agent computer also needs `ffmpeg` and an X11 size tool (`xdpyinfo` or `xwininfo`, usually in `x11-utils`).

The first connector approval, each FastFileLink share, and each Google Drive upload ask for approval. The skill tells the assistant to expect those prompts.

Useful environment variables:

| Variable | Role |
| --- | --- |
| `AGENT_RECORDER_DIR` | Recording root. Default: `~/.agent-recorder` |
| `AGENT_RECORDER_FFMPEG` | Explicit `ffmpeg` binary |

Recordings are written to `<root>/recordings/rec_YYYYMMDD_HHMMSS_<id>.mp4`.

## Tools

| Tool | Purpose |
| --- | --- |
| `startRecording` | Select this agent's display and start FFmpeg. Defaults: 5 fps, 7200 seconds. |
| `recordingStatus` | Duration, size, display, and state. `idle` when nothing is active. |
| `finishRecording` | Stop, finalize, and hand the file to a transfer strategy. |
| `confirmUpload` | Store the Google Drive link and apply `after_upload` cleanup. |
| `abortRecording` | Stop without sharing. Deletes the partial file unless `deletePartial` is false. |
| `cleanupRecording` | Delete one local recording by `recordingId` and stop its share. |

`finishRecording` defaults to `delivery=ffl` and `cleanup=after_download`. `delivery=local` with `cleanup=manual` returns a `file:` URI and leaves the file in place. `delivery=google_drive` with `cleanup=after_upload` returns `localPath` for the assistant's Google Drive connector. `confirmUpload` stores the Drive URL and then deletes the local file.

A second `startRecording` while one recording is active returns that recording and sets `alreadyRecording` to true.

## Display selection

`startRecording` looks at X11 sockets and the process tree that spawned this server (the agent, an intermediate launcher such as `uvx`, and browsers those processes started). It prefers a single browser display in that tree. Otherwise it uses the nearest `DISPLAY` on that chain.

It does not fall back to another socket. If the display cannot be identified, or a frame cannot be grabbed from it, the tool fails with:

```text
No active agent display could be identified.
```

A blank frame on the identified display is still recorded. The browser often opens after recording starts.

## Cleanup

Creating an FFL link does not delete the file. With `after_download`, the server waits until FFL reports `/download/complete` or `/webrtc/transfer/complete`, stops the share, then deletes the local file. A full HTTP download, including curl, is one of those reports. If the MCP process exits before that event, the file stays and a later `finishRecording` can share it again.

`maxDurationSeconds` stops FFmpeg and keeps a playable file so `finishRecording` can still share it. A crashed recorder does not leave FFmpeg running past that limit or after its owner process is gone.

## Skill

`.grok/skills/agent-session-recording/SKILL.md` is the install guide and the recording rule. It tells the agent to install the pinned connector when `startRecording` is missing, to call `startRecording` before browser or computer-use work, and to call `finishRecording` before the final answer.

## Development

On this machine, tests use the `recoding-mcp` conda environment.

```powershell
conda activate recoding-mcp
pip install -e .
python -m unittest discover -s tests -p "*Test.py" -v
```

`tests/Smoke.py` is a manual check for a Linux agent computer. It records for a few seconds. It does not open a browser; watch the resulting file and confirm it shows the agent display.

```powershell
python tests/Smoke.py --seconds 5 --delivery local --cleanup manual
```

Network share tests are not part of the default suite.

## Out of scope

Dashboard, accounts, tamper-proof storage, action traces, OCR, a custom browser, and Windows/macOS/Wayland capture. This server records, shares, and deletes. Google Drive upload is performed by the assistant's own Drive connector.
