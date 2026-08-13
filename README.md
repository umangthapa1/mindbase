# Mindbase AI Workspace

A comprehensive local-first AI workspace that combines a FastAPI backend with a vanilla-JS SPA frontend, powered by local Ollama models. Features include ChromaDB vector memory, SQLite storage, document Q&A, offline research, tasks/calendar with natural-language scheduling, and IMAP email integration - all running entirely on your machine with no cloud dependencies or third-party API keys.

## Table of Contents
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Backend Documentation](#backend-documentation)
- [Frontend Documentation](#frontend-documentation)
- [Development Guidelines](#development-guidelines)
- [Testing](#testing)
- [License](#license)

## Features

### Core AI Capabilities
- **Local LLM Integration**: Works with any Ollama model (default: mistral)
- **Vector Memory**: ChromaDB-backed long-term memory for context retention
- **Document Intelligence**: Upload, process, and query documents with local embeddings
- **Offline Research Agent**: Multi-step research capability without internet
- **Natural Language Processing**: Understand and execute complex requests

### Productivity Tools
- **Email Integration**: Full IMAP support for Gmail and other email providers
- **Email Automations**: Local rules that react to new mail by saving attachments, creating tasks, tagging messages, and recording notification events
- **Automation History**: A Done view with completed runs, source emails, created tasks, and downloadable saved files
- **Task Management**: Create, schedule, and track tasks with natural language
- **Calendar Integration**: Calendar view with task/event synchronization
- **Notes System**: Rich text notes with tagging and memory integration
- **Research Assistant**: Deep research capabilities with automatic note saving

### Communication & Collaboration
- **Real-time Chat**: Streaming responses with context awareness
- **Model Switching**: Change AI models on-the-fly without restart
- **Conversation History**: Persistent chat history with search
- **Conversation Export**: Export individual chat conversations as formatted `.txt` files (including correct message timestamps and roles) directly from the chat header.
- **Multi-modal Support**: Handle text, documents, and email content
- **Theme Changer**: Switch between light, dark, black-gold, blue-night, grey-ash, and Hellish Red themes via the dashboard.
- **Accent Color Selector**: Personalize the highlight color across all themes with 10 curated presets or a custom color picker — changes apply instantly and persist automatically.
- **Message Copying**: Right-click any chat message to copy its content to clipboard.
- **Full Data Backup**: Export all application data (conversations, notes, tasks, and memories) as a single JSON backup file from the Settings page.

### Security & Privacy
- **100% Local**: All data stays on your machine
- **No Third-party APIs**: Zero reliance on external AI services
- **Secure Credentials**: Email passwords stored locally with restricted permissions
- **Open Design**: Transparent codebase with clear data flow

## Theme System

Mindbase includes a comprehensive theme system that allows you to customize the visual appearance of the application. Themes can be switched at any time from the Settings page and persist via localStorage.

### Available Themes
- **Dark**: Classic dark theme with neutral accents
- **Light**: Clean light theme for daytime use
- **Black Gold**: Elegant dark theme with gold accents
- **Blue Night**: Cool dark theme with blue highlights
- **Grey Ash**: Sophisticated light theme with grey tones
- **Hellish Red**: Dramatic dark theme with vibrant red accents

### How to Change Themes
1. Open the Settings page (click the gear icon in the dock)
2. Select your preferred theme from the "Theme" dropdown
3. The change applies immediately across the entire application
4. Your selection is saved automatically and restored on future visits

All themes follow the same design principles and maintain accessibility standards for text contrast and usability.

## Accent Color System

Mindbase includes a global accent color selector that works **on top of any theme**, allowing you to personalize the highlight color used for buttons, links, focus rings, and interactive elements without changing the overall theme.

### How It Works
- The accent system overrides only the accent-related CSS variables (`--accent`, `--accent-hover`, `--accent-light`, `--accent-border`, `--accent-ring`, `--accent-glow`, `--accent-text`)
- It persists across reloads via `localStorage`
- Changes apply instantly — no reload or save button required
- Each theme has a default accent; selecting "Reset to default" restores the theme's original accent
- Works seamlessly with all six themes (Dark, Light, Black Gold, Blue Night, Grey Ash, Hellish Red)

### Available Presets
10 curated accent presets are provided:
- **Blue** (`#3B82F6`)
- **Purple** (`#8B5CF6`)
- **Violet** (`#7C3AED`)
- **Cyan** (`#06B6D4`)
- **Green** (`#22C55E`)
- **Emerald** (`#10B981`)
- **Orange** (`#F97316`)
- **Red** (`#EF4444`)
- **Pink** (`#EC4899`)
- **Yellow** (`#EAB308`)

### Custom Color Picker
In addition to presets, a **custom color picker** (🎨 button) lets you choose any hex color. The last custom color is remembered so you can easily return to it.

### How to Change the Accent
1. Open the Settings page (click the gear icon in the dock)
2. Scroll to the **Accent Color** section
3. Click any preset swatch to apply it instantly, or click the 🎨 button to pick a custom color
4. Your selection is saved automatically and restored on future visits
5. Click **Reset to default** to return to the theme's built-in accent

### Technical Details
- Implemented in `frontend/js/accent.js` as `window.MindbaseAccent`
- Computes accessible text contrast (`--accent-text`) automatically (black or white) based on WCAG luminance
- Generates hover, soft, border, ring, and glow variants from the base color
- Cross-tab synchronization via `storage` events
- Responds to theme changes — if no custom accent is active, switching themes re-derives the appropriate default accent

## Architecture

Mindbase follows a clean separation between frontend and backend:

```
mindbase/
├── backend/                  # FastAPI application (Python)
│   ├── main.py              # Application entrypoint and API routes
│   ├── config.py            # Configuration and environment variables
│   ├── database.py          # SQLAlchemy models and database management
│   ├── ollama.py            # Ollama client for LLM interactions
│   ├── intelligence.py      # Chat orchestration and context handling
│   ├── memory.py            # Long-term memory management (ChromaDB)
│   ├── documents.py         # Document processing and Q&A system
│   ├── tasks_service.py     # Task and calendar management
│   ├── research.py          # Offline research agent
│   ├── imap_service.py      # Email synchronization (IMAP)
│   └── models.py            # Pydantic models for API requests/responses
│
├── frontend/                # Vanilla JavaScript SPA
│   ├── index.html           # Main application shell
│   ├── pages/               # Individual page views
│   ├── css/                 # Stylesheets and design tokens
│   └── js/                  # Application logic and utilities
│
├── data/                    # Persistent storage (gitignored)
│   ├── workspace.db         # SQLite database
│   ├── chroma/              # ChromaDB vector store
│   └── email_config.json    # Email credentials (chmod 600)
│
└── uploads/                 # Document uploads (gitignored)
```

### Data Flow
1. **Frontend**: User interacts with vanilla-JS SPA
2. **API Layer**: Requests sent to FastAPI backend via `/api/*` endpoints
3. **Backend Services**: 
   - Route handlers in `main.py` delegate to specialized services
   - Services process requests using local resources (Ollama, DB, ChromaDB)
   - Background tasks handle email sync, research, etc.
4. **Storage**: 
   - Structured data in SQLite (`workspace.db`)
   - Vector embeddings in ChromaDB (`data/chroma/`)
   - File uploads in `uploads/`
   - Email credentials in `data/email_config.json`

## Quick Start

```bash
# Clone and enter directory
git clone https://github.com/umangthapa1/mindbase
cd mindbase

# Choose your startup method:
# Linux/macOS:
./start.sh

# Windows:
start.bat
```

The startup script will:
1. Verify Ollama is running locally
2. Create a Python virtual environment (`venv/`)
3. Install required Python packages
4. Start the FastAPI server with auto-reload
5. Open the application in your default browser at `http://localhost:8000`

## Prerequisites

- **Python 3.10+** (3.11+ recommended)
- **[Ollama](https://ollama.com)** installed and running locally
- **Required Ollama models**:
  ```bash
  ollama pull mistral          # Default chat model
  ollama pull nomic-embed-text # Required for document/memory embeddings
  ```

### Manual Setup

If you prefer to set up manually:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Start the server
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

## Configuration

All configuration is optional with sensible defaults. To customize:

1. Copy `backend/.env.example` to `backend/.env`
2. Edit the `.env` file to override defaults:

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `DEFAULT_MODEL` | `mistral` | Fallback chat model |
| `API_HOST` | `127.0.0.1` | API server bind address |
| `API_PORT` | `8000` | API server port |
| `CORS_ORIGINS` | *(unset)* | Comma-separated allow-list for CORS |
| `EMAIL_AUTO_SYNC` | `true` | Automatically sync a connected mailbox in the background |
| `EMAIL_AUTO_SYNC_INTERVAL_SECONDS` | `300` | Interval between background mailbox syncs (minimum: 60 seconds) |
| `EMAIL_AUTO_SYNC_MAX_RESULTS` | `20` | Maximum messages examined by each automatic sync |

Email credentials are stored in `backend/data/email_config.json` with file permissions set to `600` (owner-only read/write).

## Email Automations

Automations run entirely on your machine after new messages are synced from IMAP. Create a rule from **Automations** by choosing an email condition and one or more actions: save attachments, create a follow-up task, tag the email, or record a notification event.

The backend starts without waiting for the mailbox, then syncs a previously connected account in the background. It also starts an immediate background sync after an account is connected. Manual and automatic syncs share a lock to prevent overlapping runs.

Each rule is idempotent per email: the same rule cannot create duplicate tasks or artifacts for the same message. Attachments are saved locally in `uploads/email-attachments/`; files are capped at 25 MB each and 20 attachments per email. Completed work appears in **Automations → Done**, where saved files can be downloaded.

## Project Structure

For detailed documentation of each file, see the `docs/` folder:
- [Backend File Documentation](./docs/backend/)
- [Frontend File Documentation](./docs/frontend/)

## Backend Documentation

The backend consists of these key modules:

### Core Application
- **[main.py](./docs/backend/main.py.md)**: Main FastAPI application with all API routes
- **[config.py](./docs/backend/config.py.md)**: Environment configuration and path constants
- **[database.py](./docs/backend/database.py.md)**: SQLAlchemy setup, models, and migrations
- **[models.py](./docs/backend/models.py.md)**: Pydantic models for request/validation

### AI Services
- **[ollama.py](./docs/backend/ollama.py.md)**: Client for communicating with local Ollama instance
- **[intelligence.py](./docs/backend/intelligence.py.md)**: Chat orchestration, context gathering, and prompt engineering
- **[memory.py](./docs/backend/memory.py.md)**: Long-term memory management using ChromaDB
- **[documents.py](./docs/backend/documents.py.md)**: Document processing, embedding, and Q&A system
- **[research.py](./docs/backend/research.py.md)**: Offline multi-step research agent

### Productivity Services
- **[tasks_service.py](./docs/backend/tasks_service.py.md)**: Task management, calendar, and natural language date parsing
- **[imap_service.py](./docs/backend/imap_service.py.md)**: IMAP email synchronization (SSL/TLS support)
- **automations.py**: Deterministic email-rule matching, action execution, artifact tracking, and run serialization

### Supporting Modules
- Various utility modules and test files

## Frontend Documentation

The frontend is a vanilla JavaScript SPA with no build framework:

### Application Structure
- **[index.html](./docs/frontend/index.html.md)**: Main application shell containing the chat interface
- **[pages/](./docs/frontend/pages/)**: Individual HTML pages for different views:
  - [dashboard.html](./docs/frontend/pages/dashboard.html.md): Overview dashboard
  - [tasks.html](./docs/frontend/pages/tasks.html.md): Task management interface
  - [calendar.html](./docs/frontend/pages/calendar.html.md): Calendar view
  - [email.html](./docs/frontend/pages/email.html.md): Email client interface
  - [notes.html](./docs/frontend/pages/notes.html.md): Notes creation and management
  - [memory.html](./docs/frontend/pages/memory.html.md): Memory/browser interface
  - [research.html](./docs/frontend/pages/research.html.md): Research agent controls
  - [agents.html](./docs/frontend/pages/agents.html.md): AI agent configuration
  - `automations.html`: Rule builder and Done history for email automations
  - [settings.html](./docs/frontend/pages/settings.html.md): Application settings
  - [agents.html](./docs/frontend/pages/agents.html.md): AI agent configuration

### Static Assets
- **[css/globals.css](./docs/frontend/css/globals.css.md)**: CSS variables (design tokens) and base styles
- **[css/page-theme.css](./docs/frontend/css/page-theme.css.md)**: Shared chrome for all pages
- **[js/](./docs/frontend/js/)**: JavaScript modules:
  - [api.js](./docs/frontend/js/api.js.md): Wrapper for backend API calls
  - [app.js](./docs/frontend/js/app.js.md): Main application logic and routing
  - [chat.js](./docs/frontend/js/chat.js.md): Chat interface functionality
  - [dock.js](./docs/frontend/js/dock.js.md): Application dock/navigation
  - [email.js](./docs/frontend/js/email.js.md): Email-specific functionality
  - [toast.js](./docs/frontend/js/toast.js.md): Notification system
  - [utils.js](./docs/frontend/js/utils.js.md): Utility functions and helpers
  - [chat.js](./docs/frontend/js/chat.js.md): Chat message handling

## Development Guidelines

### Backend Practices
- **Logging**: Use `logging.getLogger(__name__)` in all modules, never `print()`
- **Async/Sync Balance**: FastAPI is async but SQLAlchemy is sync - offload DB calls with `asyncio.to_thread()`
- **Error Handling**: Ollama client raises exceptions - catch `OllamaError` for soft failures
- **Database Changes**: Modify `database.py::_migrate_sqlite()` with idempotent `ALTER TABLE` statements
- **CORS**: Never use `allow_origins=["*"]` with `allow_credentials=True`

### Frontend Practices
- **Styling**: Use CSS variables from `globals.css` - avoid hardcoded colors
- **No Build Step**: Plain JavaScript - no transpilation or bundling
- **Design Tokens**: All colors come from CSS `:root` variables
- **Cache Busting**: Update `?v=` query parameters when changing CSS/JS files
- **Accessibility**: Maintain proper color contrast and focus indicators

## Testing

Run the test suite to verify functionality:

```bash
# Activate virtual environment
source venv/bin/activate

# Install test dependencies
pip install -r backend/requirements-dev.txt

# Run tests
pytest backend/tests/
```

### Test Categories
- **Unit Tests**: Individual function testing in `backend/tests/`
- **Manual Verification**: Standalone scripts like `backend/test.py` and `backend/test_scheduling.py`
- **Integration**: Full system testing through manual use

## License

Mindbase is a personal/local project. No external license is declared - it's intended for individual use and learning purposes.

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern, fast web framework
- [Ollama](https://ollama.com/) - Local LLM runner
- [ChromaDB](https://www.trychroma.com/) - AI-native vector database
- [SQLAlchemy](https://www.sqlalchemy.org/) - Python SQL toolkit
- [VanillaJS](https://vanilla-js.com/) - Plain JavaScript for frontend

---

*Documentation generated automatically. For the most current information, see the source code and CLAUDE.md.*

### Achievement Workflow

Repository maintenance workflow test.

### Contribution Notes

Additional documentation maintenance.
