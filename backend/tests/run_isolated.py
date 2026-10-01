"""Run pytest against disposable storage and deterministic embeddings.

Usage (repository root):
    python backend/tests/run_isolated.py
    python backend/tests/run_isolated.py -q backend/tests/test_chat_tool_routing.py

The existing suite imports persistent singletons and includes destructive tests.
Copy only source/frontend files before any backend import, never live data or
credentials. Block network access so startup cannot contact a real mailbox/model.
This is a regression-test runner, not a live Ollama/IMAP integration test.
"""
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="mindbase-tests-") as directory:
        sandbox = Path(directory)
        for name in ("backend", "frontend"):
            shutil.copytree(root / name, sandbox / name, ignore=shutil.ignore_patterns(
                ".env*", "__pycache__", ".pytest_cache", "*.db", "*.log"))
        os.chdir(sandbox)
        os.environ.update(
            EMAIL_AUTO_SYNC="false", PYTHON_DOTENV_DISABLED="1",
            ANONYMIZED_TELEMETRY="False", OLLAMA_HOST="http://127.0.0.1:9",
            HOME=str(sandbox),
        )
        connect = socket.socket.connect

        def offline_connect(self, address):
            if self.family in (socket.AF_INET, socket.AF_INET6):
                raise OSError("Network disabled for isolated regression tests")
            return connect(self, address)

        socket.socket.connect = offline_connect
        sys.path.insert(0, str(sandbox / "backend"))
        from ollama import ollama_client

        async def embedding(*args, **kwargs):
            return [0.1, 0.2, 0.3, 0.4]

        ollama_client.generate_embedding = embedding
        import pytest
        return pytest.main(sys.argv[1:] or ["-q", "backend/tests/"])


if __name__ == "__main__":
    raise SystemExit(main())
