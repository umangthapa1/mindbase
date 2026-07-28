"""Smoke tests for memory.py note upserts.

Regression guard for the latent NameError that used to live in
`upsert_note_memory`: the `updated` variable was referenced outside the
`if existing:` branch that assigned it, so upserting a note with *no* existing
record crashed. The fix scopes the check inside the conditional; these tests
exercise both the new-record path (the former crash) and the existing-record
update path.

No live Ollama is required: embeddings are stubbed and the manager is pointed
at a fresh in-memory (ephemeral) Chroma collection per test.
"""
import asyncio

import chromadb
import pytest

from memory import memory_manager
from ollama import ollama_client


@pytest.fixture
def isolated_memory(monkeypatch):
    """Swap memory_manager onto a throwaway in-memory collection + stub embeddings."""
    client = chromadb.Client()  # ephemeral — nothing touches disk
    collection = client.get_or_create_collection(
        "smoke_memories", metadata={"hnsw:space": "cosine"}
    )
    monkeypatch.setattr(memory_manager, "collection", collection)

    async def fake_embedding(_text, _model="nomic-embed-text"):
        return [0.0, 0.0, 0.0, 0.0]

    monkeypatch.setattr(ollama_client, "generate_embedding", fake_embedding)
    return collection


def test_upsert_new_note_does_not_crash(isolated_memory):
    """No existing record → must fall through to add() instead of NameError."""
    result = asyncio.run(
        memory_manager.upsert_note_memory("smoke-1", "My Note", "Some body text", ["tag"])
    )
    assert result["id"] == "note:smoke-1"
    assert result["type"] == "reference"
    assert "My Note" in result["content"]

    got = isolated_memory.get(ids=["note:smoke-1"])
    assert "note:smoke-1" in got["ids"]


def test_upsert_existing_note_takes_update_branch(isolated_memory):
    """Same note_id twice → second call should update in place, not re-add."""
    asyncio.run(memory_manager.upsert_note_memory("smoke-2", "V1", "first body", []))
    result = asyncio.run(memory_manager.upsert_note_memory("smoke-2", "V2", "second body", []))

    assert result["id"] == "note:smoke-2"
    assert "V2" in result["content"]

    # exactly one record for this id — the second call updated, not duplicated
    got = isolated_memory.get(ids=["note:smoke-2"])
    assert got["ids"].count("note:smoke-2") == 1
