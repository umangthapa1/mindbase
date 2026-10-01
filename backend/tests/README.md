# Backend Tests

This directory contains test files for the backend components.

## Test Files

- `test.py` - Standalone test script
- `test_scheduling.py` - Schedule-related tests
- `conftest.py` - Pytest configuration
- `backend/tests/` - Pytest test suite for hot paths
- `test_chat_tool_routing.py` - Task/mail precedence, clarification, and model-free local actions
- `run_isolated.py` - Safe source-copy runner with disposable stores and stub embeddings

## Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Install test dependencies
pip install -r backend/requirements-dev.txt

# Run the real pytest suite in disposable storage, without network access
python backend/tests/run_isolated.py

# Focus on routing regressions
python backend/tests/run_isolated.py -q backend/tests/test_chat_tool_routing.py
```

Do not run the legacy full suite or `run_all_tests.py` against a valuable workspace:
its SQL override does not isolate Chroma, uploads, or application startup, and a
test intentionally clears all memories. The isolated runner copies source only,
excludes `.env`/credentials, disables mail sync/network connections, and stubs
embeddings. It checks application behavior, not real embedding quality or live
Ollama/IMAP integration. Frontend checks are documented in `frontend/tests/README.md`.
