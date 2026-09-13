# Backend Documentation

Reference pages for the FastAPI application and its local services.

## Application and services

- [`main.py`](./main.py.md) - API routes, application lifecycle, and streaming responses
- [`config.py`](./config.py.md) - Environment variables and runtime paths
- [`database.py`](./database.py.md) - SQLite engine, models, and initialization
- [`models.py`](./models.py.md) - Pydantic request and response models
- [`intelligence.py`](./intelligence.py.md) - Intent detection, context retrieval, and prompt assembly
- [`ollama.py`](./ollama.py.md) - Local Ollama generation and embeddings
- [`memory.py`](./memory.py.md) - ChromaDB-backed memory operations
- [`documents.py`](./documents.py.md) - Document ingestion and retrieval
- [`tasks_service.py`](./tasks_service.py.md) - Tasks, calendar events, and date parsing
- [`research.py`](./research.py.md) - Offline multi-step research
- [`imap_service.py`](./imap_service.py.md) - IMAP synchronization and attachments
- [`automations.py`](./automations.py.md) - Email rule matching, actions, and run history

## Configuration and tests

- [`.env.example`](./.env.example.md) - Environment template
- [`requirements.txt`](./requirements.txt.md) - Runtime dependencies
- [`requirements-dev.txt`](./requirements-dev.txt.md) - Development and test dependencies
- [`tests/`](./tests/) - Focused backend test documentation

These pages are maintained references rather than generated API output. Update the relevant page when behavior changes.
