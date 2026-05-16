# claude-chat

Iteration 1: a chat UI for your local Claude Code install.

- Lists sessions stored in SQLite.
- Creates new sessions and spawns the local `claude` CLI per turn.
- Streams `stream-json` events over WebSocket to the React UI.

No Anthropic SDK or API calls — everything goes through the `claude` binary on your PATH.

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node 20+
- `claude` CLI installed and authenticated (`claude --version` should work)

## Backend

```bash
cd backend
uv sync
uv run uvicorn claude_chat.main:app --reload --port 8000
```

The DB file `backend/claude_chat.db` is created automatically on first run.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` and `/ws` to the backend.

## How it works

- `POST /sessions` creates a row with a fresh UUID — this is the Claude Code session id.
- The first message in a session spawns `claude -p --session-id <uuid> --output-format stream-json --verbose --permission-mode bypassPermissions "<prompt>"`.
- Subsequent messages use `--resume <uuid>` so Claude Code's own session store keeps the conversation context.
- Each stdout line from the CLI is parsed as a JSON event and forwarded to the WS client; assistant text is collected and persisted on `turn_complete`.

## Known limits (iteration 1)

- `--permission-mode bypassPermissions` is on so tool calls don't block waiting for approval. Don't run this against untrusted prompts.
- No auth, single user.
- No hook capture yet — see the followup iteration to wire `PreToolUse`/`PostToolUse`/`SubagentStop` into the server for fine-grained agent state.
- No interrupt/cancel button. To stop a turn, kill the backend.
