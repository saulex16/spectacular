#!/usr/bin/env python3
"""Claude Code PreToolUse hook for intercepting subagent launches.

Claude Code calls this script before executing Agent/Task tool calls.
It sends the prompt to the claude-chat backend, waits for user approval
(with optional edits), then returns the (possibly modified) tool input.

Setup in ~/.claude/settings.json:
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [{"type": "command", "command": "python3 /home/saula/spectacular/claude-chat/backend/interceptor.py"}]
      }
    ]
  }
}

Exit codes:
  0 - allow (stdout contains modified tool_input JSON, or empty = use original)
  2 - block the tool call
"""

import json
import os
import sys
import urllib.error
import urllib.request

BACKEND = "http://localhost:8000"
TIMEOUT = 35  # slightly longer than backend's 30s long-poll


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)  # can't parse → allow through

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    session_id = os.environ.get("CLAUDE_CHAT_SESSION_ID", "unknown")

    payload = json.dumps({
        "session_id": session_id,
        "tool_name": tool_name,
        "tool_input": tool_input,
    }).encode()

    req = urllib.request.Request(
        f"{BACKEND}/intercept",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read())
    except (urllib.error.URLError, OSError):
        # Backend unreachable → allow with original input
        sys.exit(0)

    if result.get("status") == "rejected":
        print("Subagent blocked by user.", file=sys.stderr)
        sys.exit(2)

    modified = result.get("modified_input")
    if modified and modified != tool_input:
        print(json.dumps(modified))

    sys.exit(0)


if __name__ == "__main__":
    main()
