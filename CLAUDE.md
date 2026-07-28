# CLAUDE.md

Repo conventions for working in Mindbase. Read before making changes.

## Layout

- `backend/` — FastAPI app (async). Entrypoint `backend/main.py` (`uvicorn main:app`). All backend modules are flat (no package nesting); imports are top-level, e.g. `from ollama import ollama_client`.
- `frontend/` — vanilla-JS SPA, no build step, no framework. Pages are standalone HTML files in `frontend/pages/`; shared chrome in `frontend/pages/page-theme.css`; design tokens in `frontend/css/globals.css`; JS in `frontend/js/`.
- `data/` (gitignored) — SQLite + ChromaDB + `email_config.json`. `uploads/` (gitignored) — originals.

## Backend conventions

**Logging, not printing.** Every module starts with `import logging` + `logger = logging.getLogger(__name__)`. Use `logger.warning/info/debug/error("...: %s", e)` (lazy %-format, never f-strings in log calls). No `print()` in app code.

**Ollama errors are raised, not returned as strings.** `ollama_client.generate(...)` raises `OllamaError` on failure. Do **not** string-match `"[Error: ...]"` on its return value — that pattern is dead since the hardening pass. Catch `OllamaError` where you want a soft fail. Note: `stream_generate(...)` is different — it legitimately yields `"\n[Error: ...]"` markers *into* the stream (a generator can't raise mid-iteration cleanly), so stream consumers may still check for those markers.

**Don't let LLM calls hang.** Wrap long-running Ollama calls with a timeout. The established pattern is `research.py::_safe_generate` (`asyncio.wait_for(..., timeout=60.0)`); reuse it rather than inventing a new wrapper.

**DB access in async routes.** SQLAlchemy here is synchronous (`create_engine`, not async). Calling it directly inside an `async def` route blocks the event loop. Offload with `await asyncio.to_thread(...)` or `starlette.concurrency.run_in_threadpool`. Concentrate this on hot paths (`prepare_chat`, `build_schedule_context`).

**Request models.** Routes take Pydantic models (defined in `backend/models.py`), not bare `data: dict`. Add new request bodies there and reuse/extend existing models. `TagsField` accepts either a list or a comma-separated string.

**Schema changes.** No Alembic. Add new columns in `database.py::_migrate_sqlite()` as idempotent `ALTER TABLE` guards (`if "col" not in existing_cols:`). Add hot-path indexes there too. `init_db()` runs `create_all` + `_migrate_sqlite` and is called from the app lifespan (not at import time).

**CORS.** `CORS_ORIGINS` env var drives the allow-list; unset → wildcard **without** credentials (the only valid `*` combo). Never set `allow_origins=["*"]` together with `allow_credentials=True`.

**Email credentials.** `imap_service.py` writes `data/email_config.json` and chmods it `0600`. The IMAP password is plaintext at rest — keep the file owner-only; don't commit `data/`.

## Frontend conventions

**No Tailwind.** The CDN classes referenced in `frontend/js/utils.js` historically did nothing because Tailwind isn't loaded — style with CSS classes backed by the design tokens, or inline styles. Don't add new Tailwind utility classes.

**Design tokens.** Colors come from CSS variables in `frontend/css/globals.css` `:root`. The intended palette is monochrome (black/white/grey); the accent is white/light-grey, not indigo. Semantic `--ok`/`--danger` are desaturated. Don't hardcode hex literals that reintroduce color — use the vars. The one exception is the sandboxed email-rendering iframe (`email.html` srcdoc), which intentionally renders on white with normal link colors.

**Cache-busting.** CSS/JS links carry a `?v=...` query string. Bump it when you change a linked file, across every page that references it (`index.html` and the relevant `pages/*.html`).

## Testing

`backend/tests/` holds pytest smoke tests for hot paths (NL date parsing in `tasks_service.py`, memory upsert edge cases). Run from the repo root:

```bash
source venv/bin/activate
pip install -r backend/requirements-dev.txt   # pytest
pytest backend/tests/
```

`backend/test_scheduling.py` and `backend/test.py` are standalone manual scripts (run directly with `python`), not collected by pytest. `backend/conftest.py` puts `backend/` on `sys.path` so the flat top-level imports resolve when running `pytest backend/tests/` from the repo root.

## Don't reintroduce

- `print()` in backend modules.
- String-matching `"[Error"` on `ollama_client.generate()` results.
- `allow_origins=["*"]` + `allow_credentials=True`.
- Calling sync SQLAlchemy directly inside `async def` routes on hot paths.
- Indigo / saturated accent colors in the frontend.
- Gmail OAuth deps (`google-auth`, `google-auth-oauthlib`, `google-api-python-client`) — email is IMAP-only now.
