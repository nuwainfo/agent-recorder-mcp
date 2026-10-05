---
name: agent-session-recording
description: >
  Record the agent computer display around browser and computer-use work, then
  return a replay link. Use when the user asks to operate a browser, click
  through a website, use the computer UI, or wants a session replay. Call
  startRecording before the first browser or computer action and
  finishRecording before the final answer.
---

# Agent session recording

When you are going to operate a browser or computer UI on behalf of the user:

1. Call `startRecording` before the first browser or computer action. Do not pass parameters unless the user asked for a different frame rate or time limit.
2. Perform the task with the agent's own browser and computer tools.
3. After the last browser or computer action, call `finishRecording`.
4. Include the returned replay URL in the final response.
5. If recording fails, continue the task only when that is still safe, and tell the user that no replay was produced and why.
6. Record a task that does not use the browser or computer UI only when the user explicitly asks.

Do not read the video file into the conversation. The tool returns a link, not pixels.

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
