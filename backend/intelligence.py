"""
Smart chat orchestration: context retrieval, intent routing, and prompt assembly.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from documents import document_manager
from memory import memory_manager
from ollama import ollama_client
from tasks_service import task_manager, format_date_reference

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 0.42
MAX_HISTORY_MESSAGES = 28
SUMMARIZE_AFTER = 18
MAX_CONTEXT_CHARS = 12_000

# Auto-title: generate after this many messages if title still looks like a placeholder
MIN_HISTORY_FOR_TITLE = 2
PLACEHOLDER_TITLE_RE = re.compile(
    r"^(new conv|new chat|untitled|conversation|chat|\d{4}[-/ ])", re.I
)

BASE_SYSTEM = """You are Mindbase, a capable personal AI assistant running fully offline on the user's machine.

Behavior:
- Think step-by-step for hard questions; be direct for simple ones.
- Use provided context (memories, notes, documents, tasks, calendar) when relevant—cite sources naturally.
- Calendar events are saved when the user says things like "add event to calendar: … tomorrow at 3pm" — confirm what was added to the calendar when actions run.
- Tasks: "add task: …" (gets title, description, tags, priority). Updates: "set priority of X to high", "mark X as in progress".
- Meetings/events: "add event …" or "put … on my calendar".
- If context is insufficient, say what you know and what would help.
- Prefer concrete answers, examples, and actionable next steps.
- Match the user's tone; use markdown for structure when it helps."""

INTENT_HINTS = {
    "coding": (
        "The user likely wants technical help. Give correct, runnable code when asked; "
        "explain trade-offs; mention edge cases and how to verify."
    ),
    "research": (
        "The user wants depth and structure. Organize with headings; separate facts from "
        "inference; note limitations of local/offline knowledge."
    ),
    "document": (
        "Answer from the document excerpts below when possible. Quote or paraphrase the "
        "source; if the excerpts do not contain the answer, say so clearly."
    ),
    "planning": (
        "Help with tasks, priorities, and deadlines. Propose a realistic daily order: overdue first, "
        "then due today, then high priority. Be specific with dates and times from context."
    ),
    "calendar": (
        "Help with their calendar and schedule. List events and task due dates clearly by day. "
        "Warn about conflicts or overloaded days."
    ),
}
_INTENT_SIGNALS: List[Tuple[re.Pattern, str, int]] = [
    # --- document ---
    (re.compile(r"\b(document|pdf|uploaded|file says|in my doc|from the doc|according to the (file|doc))\b", re.I), "document", 3),
    (re.compile(r"\b(summarize (the|this|my) (file|doc|pdf|upload))\b", re.I), "document", 3),
    (re.compile(r"\b(excerpt|attachment)\b", re.I), "document", 2),

    # --- calendar ---
    (re.compile(r"\b(calendar|agenda|appointment)\b", re.I), "calendar", 3),
    (re.compile(r"\b(what.?s on|this week|next week|my schedule|free time|am i busy)\b", re.I), "calendar", 2),
    (re.compile(r"\b(meeting|event)\b", re.I), "calendar", 1),

    # --- planning ---
    (re.compile(r"\b(task|todo|to-do|my tasks|backlog)\b", re.I), "planning", 3),
    (re.compile(r"\b(deadline|due date|due (today|tomorrow|soon)|overdue)\b", re.I), "planning", 3),
    (re.compile(r"\b(what should i (do|focus|work)|focus today|priorit)\b", re.I), "planning", 3),
    (re.compile(r"\b(remind me|schedule|plan (my|the|for))\b", re.I), "planning", 2),
    (re.compile(r"\b(meeting|event)\b", re.I), "planning", 1),  # weaker than calendar

    # --- coding ---
    (re.compile(r"\b(code|debug|function|class|traceback|error|exception)\b", re.I), "coding", 3),
    (re.compile(r"\b(python|javascript|typescript|rust|go|sql|bash|api|endpoint|regex)\b", re.I), "coding", 3),
    (re.compile(r"\b(refactor|implement|write (a |the )?(function|class|script|test))\b", re.I), "coding", 2),

    # --- research ---
    (re.compile(r"\b(research|deep dive|literature|survey|paper|study)\b", re.I), "research", 3),
    (re.compile(r"\b(compare .+ (vs|versus|against)|pros and cons|trade.?offs?)\b", re.I), "research", 2),
    (re.compile(r"\b(explain (in depth|thoroughly|comprehensively)|how does .+ work)\b", re.I), "research", 1),
]


@dataclass
class PreparedChat:
    messages: List[Dict[str, str]]
    intent: str = "general"
    context_sources: List[str] = field(default_factory=list)
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)


class ChatIntelligence:
    def detect_intent(self, message: str) -> str:
        scores: Dict[str, float] = {}
        for pattern, intent, weight in _INTENT_SIGNALS:
            if pattern.search(message):
                scores[intent] = scores.get(intent, 0) + weight

        if not scores:
            return "general"

        # Tie-break: prefer the more specific intent when scores are equal.
        # Priority order for ties: document > calendar > planning > coding > research
        tiebreak = ["document", "calendar", "planning", "coding", "research"]
        best_score = max(scores.values())
        winners = [i for i in tiebreak if scores.get(i, 0) == best_score]
        return winners[0] if winners else max(scores, key=scores.__getitem__)

    async def _generate_title_text(
        self,
        history: List[Dict[str, str]],
        model: str,
    ) -> Optional[str]:
        """Ask the LLM for a short title based on the first few messages."""
        if len(history) < MIN_HISTORY_FOR_TITLE:
            return None

        # Use the first user message + first assistant reply for context
        snippet = "\n".join(
            f"{m['role'].capitalize()}: {m['content'][:300]}"
            for m in history[:4]
        )
        prompt = (
            "Write a short conversation title (5 words max, no quotes, no punctuation at end) "
            "that captures the main topic of this exchange:\n\n"
            f"{snippet}\n\nTitle:"
        )
        try:
            raw = await ollama_client.generate(
                model,
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return raw.strip().strip('"\'').split("\n")[0][:80]
        except Exception as e:
            logger.warning("Auto-title generation failed: %s", e)
        return None

    async def _update_title(self, conv_id: str, title: str) -> None:
        """Write the title to the DB in a worker thread using a fresh session."""
        from database import SessionLocal, ConversationDB
        from datetime import datetime

        def _commit():
            with SessionLocal() as db:
                conv = db.query(ConversationDB).filter(ConversationDB.id == conv_id).first()
                if conv and PLACEHOLDER_TITLE_RE.match(conv.title or ""):
                    conv.title = title
                    conv.updated_at = datetime.utcnow()
                    db.commit()

        try:
            await asyncio.to_thread(_commit)
        except Exception as e:
            logger.warning("Background title update failed: %s", e)

    async def _background_title(
        self,
        conv_id: str,
        history: List[Dict[str, str]],
        model: str,
    ) -> None:
        """Background title generation + update (does not block the chat stream)."""
        title = await self._generate_title_text(history, model)
        if title:
            await self._update_title(conv_id, title)

    async def maybe_generate_title(
        self,
        conv,          # ConversationDB instance
        history: List[Dict[str, str]],
        model: str,
        db: Session,
    ) -> Optional[str]:
        """
        After the first exchange, if the conversation title still looks like a
        placeholder, ask the LLM to generate a short, meaningful title.
        Returns the new title string if one was generated, else None.
        """
        if not PLACEHOLDER_TITLE_RE.match(conv.title or ""):
            return None  # already has a real title

        title = await self._generate_title_text(history, model)
        if title:
            await self._update_title(conv.id, title)
            return title
        return None

    async def _gather_memories(self, query: str, intent: str) -> tuple[str, List[str]]:
        sources: List[str] = []
        sections: List[str] = []

        profile_types = ["profile", "personal", "preference", "goal", "project"]
        profile_lines: List[str] = []

        for mem_type in profile_types:
            try:
                items = await memory_manager.get_memories_by_type(mem_type, limit=5)
            except Exception:
                items = []
            for m in items:
                line = m["content"].strip()
                if line and line not in profile_lines:
                    profile_lines.append(f"- [{mem_type}] {line}")

        if profile_lines:
            sections.append("### About the user\n" + "\n".join(profile_lines[:12]))
            sources.append("profile_memories")

        try:
            semantic = await memory_manager.search_memories(query, limit=6)
        except Exception:
            semantic = []

        relevant = [
            m
            for m in semantic
            if m.get("relevance", 0) >= RELEVANCE_THRESHOLD
        ]

        if relevant:
            lines = [
                f"- ({m.get('relevance', 0):.0%} match) {m['content'][:800]}"
                for m in relevant
            ]
            sections.append("### Relevant memories\n" + "\n".join(lines))
            sources.append("semantic_memory")

        if intent in ("research", "general", "planning"):
            try:
                note_hits = await memory_manager.get_note_memories(limit=3)
                if not note_hits:
                    hits = await memory_manager.search_memories(query, limit=5)
                    note_hits = [
                        m
                        for m in hits
                        if (m.get("metadata") or {}).get("source") == "note"
                        or "note" in (m.get("tags") or [])
                    ]
                if note_hits:
                    note_text = "\n\n".join(
                        m["content"][:1200] for m in note_hits[:3]
                    )
                    sections.append("### Related notes\n" + note_text)
                    sources.append("notes")
            except Exception:
                pass

        return "\n\n".join(sections), sources

    async def _gather_documents(self, query: str, intent: str) -> tuple[str, List[str]]:
        try:
            docs = await document_manager.list_documents()
            if not docs:
                return "", []
        except Exception:
            return "", []

        should_search = intent == "document" or re.search(
            r"\b(summarize|upload|file|document|pdf|excerpt|according to)\b",
            query.lower(),
        )
        if not should_search:
            return "", []

        try:
            result = await document_manager.search_documents(query, top_k=4)
        except Exception:
            return "", []

        chunks = result.get("chunks") or []
        if not chunks:
            return "", []

        lines = []
        for c in chunks:
            fname = c.get("filename", "document")
            lines.append(f"**{fname}** (chunk {c.get('chunk_index', '?')}):\n{c['text'][:900]}")

        return "### Document excerpts\n" + "\n\n".join(lines), ["documents"]

    async def _gather_schedule(self, db: Session, query: str, intent: str) -> tuple[str, List[str]]:
        # Don't inject tasks/calendar into email queries — it causes the LLM to
        # hallucinate task details instead of reading the Gmail context.
        email_terms = re.compile(
            r"(check|show|get|read|fetch|list|see|find|any|have).{0,40}(email|gmail|mail|inbox|message)"
            r"|(email|gmail|mail|inbox|message).{0,40}(check|show|unread|new|recent)"
            r"|\binbox\b|\bgmail\b|(unread|unopened).{0,20}(email|mail)",
            re.I
        )
        if email_terms.search(query):
            return "", []

        full = intent in ("planning", "calendar") or bool(
            re.search(
                r"\b(today|tomorrow|week|focus|plan|overdue|calendar|schedule|task|todo)\b",
                query.lower(),
            )
        )
        # `build_schedule_context` is synchronous SQLAlchemy work. Run it in a
        # worker thread so the async event loop stays free for other requests while
        # SQLite is queried. The DB session is not shared across threads — the thread
        # opens a fresh SessionLocal for the duration of the call.
        def _build():
            from database import SessionLocal
            with SessionLocal() as fresh_db:
                return task_manager.build_schedule_context(fresh_db, query, intent, full=full)

        return await asyncio.to_thread(_build)

    async def _maybe_summarize_history(
        self, messages: List[Dict[str, str]], model: str
    ) -> List[Dict[str, str]]:
        if len(messages) <= SUMMARIZE_AFTER:
            return messages

        keep_recent = MAX_HISTORY_MESSAGES // 2
        old = messages[:-keep_recent]
        recent = messages[-keep_recent:]

        transcript = "\n".join(
            f"{m['role']}: {m['content'][:400]}" for m in old[-20:]
        )
        prompt = (
            "Summarize this conversation for continuity. "
            "Keep: decisions made, key facts stated, open questions, user preferences. "
            "Be concise — 3 to 5 bullet points, max 150 words. No intro sentence.\n\n"
            f"{transcript}\n\nSummary:"
        )

        try:
            summary = await ollama_client.generate(
                model, [{"role": "user", "content": prompt}], temperature=0.3
            )
            if summary:
                return [
                    {
                        "role": "system",
                        "content": f"Earlier conversation summary:\n{summary.strip()}",
                    },
                    *recent,
                ]
        except Exception:
            pass

        return recent

    def _trim_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        total = sum(len(m.get("content", "")) for m in messages)
        if total <= MAX_CONTEXT_CHARS:
            return messages

        trimmed = []
        budget = MAX_CONTEXT_CHARS
        for m in reversed(messages):
            content = m.get("content", "")
            if len(content) > budget and m["role"] != "system":
                content = content[:budget] + "\n…[truncated]"
            trimmed.insert(0, {**m, "content": content})
            budget -= len(content)
            if budget <= 0 and m["role"] != "system":
                break
        return trimmed

    async def prepare_chat(
        self,
        *,
        user_message: str,
        history: List[Dict[str, str]],
        db: Session,
        model: str,
        agent_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        actions_taken: Optional[List[Dict[str, Any]]] = None,
        conv=None,  # ConversationDB instance, optional — used for auto-titling
    ) -> PreparedChat:
        intent = self.detect_intent(user_message)
        sources: List[str] = []
        actions_taken = actions_taken or []

        context_parts: List[str] = []

        # Gather schedule, memory, and document contexts in parallel. All three are
        # I/O-bound (SQLite/Chroma/Ollama embeddings) so concurrency here directly
        # reduces first-token latency. `_gather_schedule` runs its SQLAlchemy work in
        # a worker thread so it doesn't block the event loop.
        (schedule_ctx, sched_src), (mem_ctx, mem_src), (doc_ctx, doc_src) = await asyncio.gather(
            self._gather_schedule(db, user_message, intent),
            self._gather_memories(user_message, intent),
            self._gather_documents(user_message, intent),
        )
        if schedule_ctx:
            context_parts.append(schedule_ctx)
            sources.extend(sched_src)
        if mem_ctx:
            context_parts.append(mem_ctx)
            sources.extend(mem_src)
        if doc_ctx:
            context_parts.append(doc_ctx)
            sources.extend(doc_src)

        system = BASE_SYSTEM + f"\n\n## Current date\n{format_date_reference()}"
        if actions_taken:
            action_lines = "\n".join(
                f"- {a['message']}" for a in actions_taken if a.get("success")
            )
            failed = [a for a in actions_taken if not a.get("success")]
            if action_lines:
                system += (
                    f"\n\n## Actions just performed (REAL — already saved)\n{action_lines}\n"
                    "Confirm briefly. Tell them to open the Calendar page to see it."
                )
            for a in failed:
                system += f"\n(Action failed: {a.get('message')})"
        elif intent in ("calendar", "planning") or re.search(
            r"\b(calendar|calender|schedule|event|meeting)\b", user_message.lower()
        ):
            system += (
                "\n\n## CRITICAL\nNo calendar/task action ran this turn. "
                "Do NOT say anything was added to the calendar. "
                "Ask them to retry in one message, e.g. "
                "'put Monaco Grand Prix on my calendar for Sunday at 6:45pm to 7:45pm'."
            )

        if agent_prompt:
            system = f"{system}\n\n{agent_prompt.strip()}"
        if hint := INTENT_HINTS.get(intent):
            system += f"\n\n## Mode: {intent}\n{hint}"

        if context_parts:
            ctx_block = "\n\n".join(context_parts)
            if len(ctx_block) > MAX_CONTEXT_CHARS:
                ctx_block = ctx_block[:MAX_CONTEXT_CHARS] + "\n…[context truncated]"
            system += f"\n\n---\n## Retrieved context (use when relevant)\n{ctx_block}"

        chat_messages = [{"role": m["role"], "content": m["content"]} for m in history]
        chat_messages = await self._maybe_summarize_history(chat_messages, model)
        chat_messages = self._trim_messages(chat_messages)
        chat_messages.insert(0, {"role": "system", "content": system})

        return PreparedChat(
            messages=chat_messages,
            intent=intent,
            context_sources=sources,
            actions_taken=actions_taken,
        )


chat_intelligence = ChatIntelligence()
