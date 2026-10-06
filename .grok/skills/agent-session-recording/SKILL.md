---
name: agent-session-recording
description: >
  Record the agent computer display around browser and computer-use work, then
  return a replay link. Use when the user asks to operate a browser, click
  through a website, use the computer UI, or wants a session replay. If
  startRecording is not available, install the pinned MCP connector for this
  assistant first. Call startRecording before the first browser or computer
  action and finishRecording before the final answer.
---

# Agent session recording

Pinned source, tag `v0.1.0`:

```text
git+https://github.com/nuwainfo/agent-recorder-mcp.git@v0.1.0
```

Install and launch only that tag. Do not follow the default branch.

## Install the connector when the tool is missing

Before any browser or computer action, check whether `startRecording` is available.

If it is missing, install the connector for this assistant, then call `startRecording`. The agent computer also needs `ffmpeg` and `xdpyinfo` or `xwininfo`.

Adding a connector asks for approval. A FastFileLink share asks for approval. A Google Drive upload asks for approval. Those prompts stay. Tell the user the first run needs those approvals.

### Grok Bot

Add a custom connector. This is not the Grok Build config file.

- Command: `uvx`
- Args: `--from git+https://github.com/nuwainfo/agent-recorder-mcp.git@v0.1.0 agent-recorder-mcp`

### Claude Code

```bash
claude mcp add-json agent-recorder --scope user "{\"command\":\"uvx\",\"args\":[\"--from\",\"git+https://github.com/nuwainfo/agent-recorder-mcp.git@v0.1.0\",\"agent-recorder-mcp\"]}"
```

### Claude Desktop

Add this entry to `claude_desktop_config.json` under `mcpServers`:

```json
"agent-recorder": {
  "command": "uvx",
  "args": ["--from", "git+https://github.com/nuwainfo/agent-recorder-mcp.git@v0.1.0", "agent-recorder-mcp"]
}
```

### Codex

Add this block to `~/.codex/config.toml`:

```toml
[mcp_servers.agent-recorder]
command = "uvx"
args = ["--from", "git+https://github.com/nuwainfo/agent-recorder-mcp.git@v0.1.0", "agent-recorder-mcp"]
```

### Cursor

Add the same `agent-recorder` entry used for Claude Desktop to `~/.cursor/mcp.json` under `mcpServers`.

### Grok Build

`agent-recorder-mcp install --target grok-build` writes `~/.grok/config.toml`. Use that only for Grok Build. Grok Bot uses the custom connector above.

## Record

When you are going to operate a browser or computer UI on behalf of the user:

1. Call `startRecording` before the first browser or computer action. Pass `fps` or `maxDurationSeconds` only when the user asked for them. For a FastFileLink replay, omit `outputDir`. For Google Drive, set `outputDir` to a folder the Drive upload tool can read, such as `/workspace`.
2. Perform the task with the agent's own browser and computer tools.
3. After the last browser or computer action, call `finishRecording`.
4. Include the returned replay URL in the final response.
5. If recording fails, continue the task only when that is still safe, and tell the user that no replay was produced and why.
6. Record a task that does not use the browser or computer UI only when the user explicitly asks.

Do not read the video file into the conversation. The tool returns a link, not pixels.

`finishRecording` defaults to FastFileLink. The local file stays until the recipient finishes downloading, including a full HTTP download such as curl. The share then stops and the file is deleted.

## Google Drive

Use this only when the user wants the replay on Google Drive and a Google Drive connector is available. This recorder does not call Google.

1. Call `startRecording` with `outputDir` set to a folder the upload tool can read. Use `/workspace` when that is the readable folder. The recording file is written there. Do not copy it anywhere else.
2. Call `finishRecording` with `delivery` `google_drive` and `cleanup` `after_upload`.
3. Upload the returned `localPath` with the Google Drive connector. Do not read the video into the chat.
4. Call `confirmUpload` with `recordingId` and the Drive file URL the connector returned. That deletes the file at `localPath`.
5. Put that Drive URL in the final response.

If no Google Drive connector is connected, use the default `finishRecording` and return the FastFileLink URL.

## Final response

Write the whole reply in the language the user is speaking. The labels below are English. Translate them, including the failure sentence. Leave the replay URL unchanged.

When a replay exists:

```text
Done.

Result:
<work result>

Session replay:
<replay URL>
```

When it does not:

```text
Done.

Result:
<work result>

Session replay:
Recording failed. No replay was produced.
Reason: <error>
```
