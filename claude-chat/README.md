# claude-chat

Chat UI with multiple AI backends.

## Modes

| Mode | Provider id | Requirements |
|------|-------------|--------------|
| **Claude CLI** (default) | `claude_cli` | `claude` on PATH, authenticated locally |
| **Anthropic API** | `anthropic` | API key in Settings |
| **OpenAI API** | `openai` | API key in Settings |
| **Google Gemini API** | `google` | API key in Settings |

API modes use [Pydantic AI](https://ai.pydantic.dev/) in-process with coding tools (`read_file`, `write_file`, `list_directory`, `run_bash`) scoped to the session `cwd`.

**Subagent tabs** (Task/Agent) are only available in Claude CLI mode. API subagents are planned for a future release.

## Prerequisites

- Python 3.10+ and [uv](https://docs.astral.sh/uv/)
- Node 20+
- For Claude CLI mode: `claude --version` should work

## Configuration

Copy `backend/.env.example` to `backend/.env` and set:

```bash
CREDENTIALS_ENCRYPTION_KEY=<output of Fernet.generate_key()>
```

Without this key, the server uses an ephemeral key (credentials lost on restart).

API keys are stored encrypted in SQLite via the Settings panel (⚙ in the sidebar). They are never returned in full to the client.

## Backend

```bash
cd backend
uv sync
uv run uvicorn claude_chat.main:app --reload --port 8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/ws` to the backend.

## Creating sessions

Use **+ New** in the sidebar to pick a provider and model, then **Create session**. Existing sessions default to `claude_cli` after upgrade.

## Tests

```bash
cd backend
uv sync --extra dev
uv run pytest
```

## Roadmap (v2)

- Subagents for API providers via a custom `task` tool on Pydantic AI
- Optional confirmation UI for `run_bash` in API mode
