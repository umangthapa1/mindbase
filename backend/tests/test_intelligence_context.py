"""Regression coverage for parallel chat-context gathering."""
import asyncio

from intelligence import chat_intelligence


def test_prepare_chat_unpacks_parallel_context_results(monkeypatch):
    """Each gatherer returns a (context, sources) pair, not six flat values."""
    async def schedule(*_args):
        return "schedule context", ["tasks"]

    async def memories(*_args):
        return "memory context", ["memories"]

    async def documents(*_args):
        return "document context", ["documents"]

    monkeypatch.setattr(chat_intelligence, "_gather_schedule", schedule)
    monkeypatch.setattr(chat_intelligence, "_gather_memories", memories)
    monkeypatch.setattr(chat_intelligence, "_gather_documents", documents)

    prepared = asyncio.run(
        chat_intelligence.prepare_chat(
            user_message="What should I focus on?",
            history=[],
            db=None,
            model="test-model",
        )
    )

    assert prepared.context_sources == ["tasks", "memories", "documents"]
    system = prepared.messages[0]["content"]
    assert "schedule context" in system
    assert "memory context" in system
    assert "document context" in system
