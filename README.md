# Mindbase

### A local-first AI workspace for thinking, planning, and getting things done.

Mindbase brings chat, memory, notes, documents, email, tasks, calendar events, and offline research into one private workspace. It runs on your machine using [Ollama](https://ollama.com/), so your workspace data stays local and the core AI features do not require cloud API keys.

> **Status:** Personal project in active development. The application is usable, but interfaces and APIs may evolve.

## What it does

- **Chat with context** from your memories, notes, documents, tasks, calendar, and synced email.
- **Remember important information** with a ChromaDB-backed long-term memory store.
- **Ask questions about documents** using local embeddings and retrieval.
- **Manage tasks and calendar events** with natural-language scheduling.
- **Work with email** through IMAP, including local email search and deterministic automations.
- **Research offline** with a multi-step local research assistant.
- **Write notes** with Markdown, preview mode, tagging, and debounced auto-save.
- **Personalize the workspace** with themes, background patterns, and accent colors.

## Quick start

### 1. Install the prerequisites

- Python 3.10 or newer (3.11+ recommended)
- [Ollama](https://ollama.com/) installed and running

Pull one chat model and the embedding model used by memory and documents:

```bash
ollama pull mistral
ollama pull nomic-embed-text
```

You can use another Ollama chat model by changing `DEFAULT_MODEL` or selecting one from Settings.

### 2. Start Mindbase

On Linux or macOS:

```bash
git clone https://github.com/umangthapa1/mindbase.git
cd mindbase
chmod +x start.sh
./start.sh
```

On Windows, run:

```text
start.bat
```

The startup script checks Ollama, creates `venv/` when needed, installs backend dependencies, and starts the development server with auto-reload.

Open **[http://localhost:8000](http://localhost:8000)** when the server is ready.

### Manual setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

## Main areas

| Area | Purpose |
| --- | --- |
| Chat | Streaming conversations with local model selection and workspace context |
| Dashboard | Overview of activity, tasks, events, and workspace status |
| Notes | Markdown notes with preview, tagging, and memory integration |
| Documents | Upload documents, search their content, and ask questions |
| Memory | Browse, search, and manage long-term workspace memories |
| Tasks | Track priorities, status, tags, and natural-language due dates |
| Calendar | View and manage events alongside scheduled tasks |
| Email | Sync and search an IMAP mailbox locally |
| Automations | Run email rules that save attachments, create tasks, tag messages, and record runs |
| Research | Generate structured research reports locally and save them to notes |
| Settings | Configure models, response length, memory behavior, themes, accents, export, and reset actions |

## Email automations

Email automations run locally after new messages are synced from IMAP. Create rules from **Automations** by choosing a condition and one or more actions:

- Save attachments to `uploads/email-attachments/`
- Create a follow-up task
- Add a tag to the email
- Record an auditable event in the **Done** list

Rules are idempotent per rule and email, so repeated syncs do not create duplicate work. Attachments are limited to 25 MB each and 20 attachments per email. The current `notify` action records an event locally; it does not send push or desktop notifications.

## Privacy and local storage

Mindbase is designed for local use:

- Chat generation and embeddings run through your local Ollama instance.
- Structured data is stored in SQLite at `data/workspace.db`.
- Vector memory is stored in `data/chroma/`.
- Uploaded files are stored in `uploads/`.
- Email credentials are stored locally in `data/email_config.json` with owner-only permissions.

Keep `data/` and `uploads/` out of version control. Email app passwords are stored in plaintext locally, so protect the machine and the credentials file.

### Destructive actions

Bulk deletion requires both UI confirmation and an exact confirmation token in the request body:

| Action | Endpoint | Required body |
| --- | --- | --- |
| Delete all data | `POST /api/reset` | `{"confirm": "DELETE EVERYTHING"}` |
| Clear memories | `POST /api/memory/clear` | `{"confirm": "CLEAR MEMORIES"}` |

These operations do not remove `data/email_config.json`. Disconnect a mailbox separately with `POST /api/email/disconnect`.

## Configuration

Mindbase works with defaults, but environment variables can be used to customize the server. Copy the included example to `backend/.env`:

```bash
cp backend/.env.example backend/.env
```

| Variable | Default | Description |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `DEFAULT_MODEL` | `mistral` | Fallback chat model |
| `API_HOST` | `127.0.0.1` | API bind address |
| `API_PORT` | `8000` | API port |
| `CORS_ORIGINS` | unset | Comma-separated CORS allow-list |
| `EMAIL_AUTO_SYNC` | `true` | Sync a connected mailbox in the background |
| `EMAIL_AUTO_SYNC_INTERVAL_SECONDS` | `300` | Background sync interval; minimum 60 seconds |
| `EMAIL_AUTO_SYNC_MAX_RESULTS` | `20` | Maximum messages examined per automatic sync |

The application creates its data directories automatically on startup.

## Architecture

```text
Browser
  |
  |  Vanilla HTML, CSS, and JavaScript
  v
FastAPI application
  |
  +-- Chat orchestration and streaming
  +-- Tasks, calendar, notes, documents, and email services
  +-- SQLite for structured records
  +-- ChromaDB for vector memory
  +-- Ollama for local generation and embeddings
```

The frontend has no build step. The backend is a FastAPI application with synchronous SQLAlchemy persistence and asynchronous service integrations.

## Project structure

```text
mindbase/
├── backend/
│   ├── main.py             # FastAPI application and API routes
│   ├── config.py           # Environment configuration and data paths
│   ├── database.py         # SQLAlchemy models and initialization
│   ├── intelligence.py     # Chat intent, context, and prompt assembly
│   ├── ollama.py            # Local Ollama client
│   ├── memory.py            # ChromaDB memory operations
│   ├── documents.py         # Document processing and retrieval
│   ├── tasks_service.py     # Tasks, calendar, and date parsing
│   ├── imap_service.py      # IMAP synchronization
│   ├── automations.py       # Email rules and automation run history
│   ├── research.py          # Offline research agent
│   └── tests/                # Focused backend tests
├── frontend/
│   ├── index.html            # Main chat application
│   ├── pages/                # Dashboard and workspace pages
│   ├── css/                  # Shared styles and design tokens
│   └── js/                   # Frontend modules and API client
├── data/                     # Local runtime data; gitignored
├── uploads/                  # Local uploads; gitignored
├── start.sh                 # Linux/macOS startup script
└── start.bat                # Windows startup script
```

Detailed file documentation is available in [`docs/`](./docs/), including [backend documentation](./docs/backend/) and [frontend documentation](./docs/frontend/).

## Development

Backend dependencies:

```bash
source venv/bin/activate
pip install -r backend/requirements-dev.txt
```

Useful development practices:

- Use the project logger instead of `print()` in backend modules.
- Offload synchronous SQLAlchemy work from async routes with `asyncio.to_thread()` when appropriate.
- Catch `OllamaError` for recoverable local model failures.
- Keep database migrations idempotent.
- Use the shared CSS variables in `frontend/css/globals.css`.
- Preserve accessibility, focus states, and keyboard interaction when changing the UI.

## Testing

Run the backend test suite from the repository root:

```bash
source venv/bin/activate
pip install -r backend/requirements-dev.txt
pytest -q backend/tests/
```

Current coverage includes natural-language due dates, memory upserts, email query routing, chat context assembly, and email automations. The standalone scripts `backend/test.py` and `backend/test_scheduling.py` are manual checks rather than pytest tests.

## Documentation

- [Backend documentation](./docs/backend/)
- [Frontend documentation](./docs/frontend/)
- [Backend README](./backend/README.md)
- [Frontend README](./frontend/README.md)

## License

No external license is currently declared. Mindbase is a personal/local project intended for individual use and learning.

## Built with

[FastAPI](https://fastapi.tiangolo.com/) · [Ollama](https://ollama.com/) · [ChromaDB](https://www.trychroma.com/) · [SQLAlchemy](https://www.sqlalchemy.org/) · [Vanilla JS](https://vanilla-js.com/)
