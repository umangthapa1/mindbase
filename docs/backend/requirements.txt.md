# `backend/requirements.txt`

Production Python dependencies for the FastAPI application.

The file contains the runtime stack for:

- FastAPI and Uvicorn for the HTTP API.
- SQLAlchemy for SQLite persistence.
- HTTPX for Ollama and remote service requests.
- ChromaDB and embedding-related packages for vector memory.
- Document parsing, IMAP, and supporting utility libraries.

Install from the repository root with:

```bash
python -m pip install -r backend/requirements.txt
```

The startup script installs this file automatically when `venv/bin/uvicorn` is not present.
