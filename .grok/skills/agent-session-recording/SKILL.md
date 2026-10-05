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

1. Call `startRecording` before the first browser or computer action. Do not pass parameters unless the user asked for a different frame rate or time limit.
2. Perform the task with the agent's own browser and computer tools.
3. After the last browser or computer action, call `finishRecording`.
4. Include the returned replay URL in the final response.
5. If recording fails, continue the task only when that is still safe, and tell the user that no replay was produced and why.
6. Record a task that does not use the browser or computer UI only when the user explicitly asks.

Do not read the video file into the conversation. The tool returns a link, not pixels.

`finishRecording` defaults to FastFileLink. The local file stays until the recipient finishes downloading, including a full HTTP download such as curl. The share then stops and the file is deleted.

## Google Drive

Use this only when the user wants the replay on Google Drive and a Google Drive connector is available. This recorder does not call Google.

1. Call `finishRecording` with `delivery` `google_drive` and `cleanup` `after_upload`.
2. Upload the returned `localPath` with the Google Drive connector. Do not read the video into the chat.
3. Call `confirmUpload` with `recordingId` and the Drive file URL the connector returned.
4. Put that Drive URL in the final response.

If no Google Drive connector is connected, use the default `finishRecording` and return the FastFileLink URL.

Final response when a replay exists:

```text
完成。

結果：
<work result>

操作錄影：
<replay URL>
```

Final response when it does not:

```text
完成。

結果：
<work result>

操作錄影：
這次錄影失敗，沒有產生 replay。
原因：<error>
```
