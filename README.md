# Mindbase

A local-first AI workspace. FastAPI backend + vanilla-JS SPA frontend, powered by a local Ollama model, with ChromaDB vector memory, SQLite storage, document Q&A, offline research, tasks/calendar with natural-language scheduling, and IMAP email integration. Everything runs on your machine — no cloud, no API keys to a third party.

## Quick start

```bash
./start.sh
```

The script checks that Ollama is reachable, creates a `venv/`, installs `backend/requirements.txt`, and starts uvicorn with `--reload`. Open <http://localhost:8000>.

### Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com)** running locally (`ollama serve`) with at least one chat model pulled:
  ```bash
  ollama pull mistral          # default model
  ollama pull nomic-embed-text # required for document/memory embeddings
  ```

On Windows use `start.bat` instead of `start.sh`.

### Manual run

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

## Configuration

All settings are optional — sensible defaults work for a single-user local install. Copy `backend/.env.example` to `backend/.env` and override as needed:

| Variable        | Default                  | Purpose                                                      |
|-----------------|--------------------------|--------------------------------------------------------------|
| `OLLAMA_HOST`   | `http://localhost:11434` | Ollama server URL                                            |
| `DEFAULT_MODEL` | `mistral`                | Fallback chat model when none is selected                    |
| `API_HOST`      | `127.0.0.1`              | Bind address for the API server                              |
| `API_PORT`      | `8000`                   | API server port                                              |
| `CORS_ORIGINS`  | *(unset → wildcard)*     | Comma-separated allow-list, e.g. `http://localhost:8000`. When set, credentials are allowed; when unset, a permissive wildcard is used **without** credentials (the only valid combination for `*`). |

Email credentials are stored separately in `backend/data/email_config.json` (chmod `0600`, owner-only). The IMAP password is the only sensitive value the app persists; it is **not** encrypted at rest — if that matters to you, keep the file's permissions tight and don't sync `data/` to shared storage.

## Architecture

```
frontend/                 Vanilla-JS SPA (no build step)
  index.html              Chat shell + model selector
  pages/*.html            Tasks, calendar, documents, email, memory,
                          notes, research, agents, settings, dashboard
  css/globals.css         Design tokens + base theme
  pages/page-theme.css    Shared page chrome
  js/                     api.js (fetch wrapper), chat.js, app.js, dock.js, ...

backend/                  FastAPI (async)
  main.py                 Routes, request models, SSE chat streaming, lifespan
  config.py               Env-driven settings + path constants
  database.py             SQLAlchemy models + _migrate_sqlite() + get_db()
  ollama.py               Ollama HTTP client (chat, embeddings, pull, health)
  intelligence.py         Chat orchestration: context retrieval, intent, prompts
  memory.py               ChromaDB-backed long-term memory + note upserts
  documents.py            Upload, chunk, embed, vector search, Q&A, summaries
  tasks_service.py        Tasks + calendar + NL date parsing + chat scheduling
  research.py             Offline multi-step research agent
  imap_service.py         IMAP inbox sync (stdlib only, no OAuth)
  models.py               Pydantic request/response models
```

**Storage**
- `data/workspace.db` — SQLite (conversations, messages, notes, tasks, events, emails).
- `data/chroma/` — ChromaDB persistent vector store (documents, memories).
- `uploads/` — original uploaded documents.

**Request flow (chat):** `POST /api/chat/messages` (SSE) → `intelligence.prepare_chat` gathers memory + document + schedule context → Ollama streams the reply token-by-token; side effects (task/event creation) run on the same turn.

## Development notes

- The backend is async FastAPI but uses **synchronous SQLAlchemy**. DB calls inside async routes should be offloaded with `asyncio.to_thread(...)` (or Starlette's `run_in_threadpool`) so they don't block the event loop — see `CLAUDE.md` for the established patterns.
- Schema changes go through `database.py::_migrate_sqlite()` (ad-hoc `ALTER TABLE`); there is no Alembic migration tooling yet.
- Logging uses the stdlib `logging` module — every backend module declares `logger = logging.getLogger(__name__)`. Avoid `print()`.
- Tests: `pip install -r backend/requirements-dev.txt && pytest backend/tests/` runs the smoke tests (NL date parsing in `tasks_service.py`, memory upsert edge cases). See `CLAUDE.md` for conventions.

## License

Personal/local project. No upstream license declared.

## Recent UI improvements (July 2026)

- Enhanced keyboard focus visibility with added depth for better accessibility.
- Improved stat card interactions with hover lift and active press feedback.
- Enlarged dock items for easier touch targeting and refined hover animation.
- Refined toast notifications with increased padding and polished entrance/exit animations.
- Added subtle glow effect to active dock items for stronger navigation feedback.