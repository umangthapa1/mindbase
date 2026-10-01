"""Measure real chat preparation without touching the user's workspace.

Run with the existing venv from the repository root:
    python backend/benchmarks/benchmark_chat_routing.py --samples 3

Copies application source (not data/credentials) to a temporary workspace. Uses
in-memory SQL, disables auto-sync/memory/title generation, and calls the existing
local Ollama service with synthetic prompts. Reports time to first content plus
model-discovery/generation calls. One warmup per workload is excluded.
"""
import argparse
import asyncio
from collections import defaultdict
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import time


async def measure(samples, timeout):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import Base, TaskDB, ConversationDB
    from main import send_message
    from models import ChatRequest
    from ollama import ollama_client, aclose

    stats = defaultdict(list)
    for name in ("list_models", "generate", "generate_embedding"):
        original = getattr(ollama_client, name)

        async def timed(*args, _name=name, _original=original, **kwargs):
            started = time.perf_counter()
            try:
                return await _original(*args, **kwargs)
            finally:
                stats[_name].append((time.perf_counter() - started) * 1000)
        setattr(ollama_client, name, timed)

    async def turn(message):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        try:
            with sessionmaker(bind=engine)() as db:
                conv = ConversationDB(title="Routing benchmark")
                db.add(conv)
                db.commit()
                stats.clear()
                started = time.perf_counter()
                response = await send_message(ChatRequest(
                    conversation_id=conv.id, message=message,
                    include_memory=False, auto_memory=False,
                ), db)
                first_content = None
                action = None
                async for frame in response.body_iterator:
                    data = json.loads(frame.removeprefix("data: ").strip())
                    if data.get("meta"):
                        action = data["meta"].get("actions")
                    if data.get("chunk") and first_content is None:
                        first_content = (time.perf_counter() - started) * 1000
                expected_tasks = 1 if message.startswith("add task") else 0
                assert db.query(TaskDB).count() == expected_tasks, "Workload behavior changed"
                if expected_tasks:
                    task = db.query(TaskDB).one()
                    assert "milk" in task.title.lower() and task.due_date is not None
                return {
                    "first_content_ms": round(first_content, 2),
                    "calls": {name: len(values) for name, values in stats.items()},
                    "stage_ms": {name: round(sum(values), 2) for name, values in stats.items()},
                    "actions": [a.get("action") for a in (action or [])],
                }
        finally:
            engine.dispose()

    try:
        for message in ("add task: Buy milk tomorrow", "any new mail?"):
            warmup = await asyncio.wait_for(turn(message), timeout)
            runs = [await asyncio.wait_for(turn(message), timeout) for _ in range(samples)]
            print(json.dumps({
                "message": message, "warmup": warmup, "runs": runs,
                "median_first_content_ms": statistics.median(r["first_content_ms"] for r in runs),
            }), flush=True)
    finally:
        await aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=75, help="Seconds per request")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    backend = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="mindbase-benchmark-") as directory:
        sandbox = Path(directory)
        shutil.copytree(backend, sandbox / "backend", ignore=shutil.ignore_patterns(
            ".env*", "__pycache__", ".pytest_cache", "*.db", "*.log"))
        # main mounts this directory; the benchmark never serves frontend files.
        (sandbox / "frontend").mkdir()
        os.environ.update(EMAIL_AUTO_SYNC="false", PYTHON_DOTENV_DISABLED="1", ANONYMIZED_TELEMETRY="False")
        sys.path.insert(0, str(sandbox / "backend"))
        asyncio.run(measure(args.samples, args.timeout))


if __name__ == "__main__":
    main()
