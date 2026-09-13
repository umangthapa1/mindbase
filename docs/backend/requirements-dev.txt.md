# `backend/requirements-dev.txt`

Development-only dependencies. This file extends the production requirements with the tools needed to run the backend test suite.

```bash
python -m pip install -r backend/requirements-dev.txt
pytest -q backend/tests/
```
