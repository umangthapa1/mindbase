"""Pytest bootstrap for backend tests.

Backend modules use top-level imports (e.g. `from ollama import ollama_client`),
so `backend/` must be on sys.path when tests run as `pytest backend/tests/` from
the repo root. This conftest lives in `backend/` and prepends its own directory.
"""
import os
import sys

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
