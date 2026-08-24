from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager, suppress
import json
import re as _re
import logging
import asyncio
import threading
from typing import Optional

from config import API_HOST, API_PORT, DEFAULT_MODEL, BASE_DIR, CORS_ORIGINS, CORS_ALLOW_CREDENTIALS, EMAIL_AUTO_SYNC, EMAIL_AUTO_SYNC_INTERVAL_SECONDS, EMAIL_AUTO_SYNC_MAX_RESULTS
from imap_service import email_service, serialize_email, ATTACHMENTS_DIR
from database import init_db, get_db, ConversationDB, MessageDB, SessionLocal, NoteDB, TaskDB, CalendarEventDB, EmailDB, AutomationRuleDB, AutomationRunDB, EmailAttachmentDB, AutomationArtifactDB
from tasks_service import task_manager, serialize_task, serialize_event, _parse_date_string
from models import (
    Conversation, ConversationCreate, ConversationUpdate, ChatRequest, ChatResponse, Message,
    ModelSwitchRequest, MemoryCreate, MemorySearch, MemoryUpdate,
    NoteCreate, NoteUpdate, TaskCreate, TaskUpdate,
    CalendarEventCreate, CalendarEventUpdate,
    ResearchRequest, ResearchSaveRequest, DocumentAsk,
    EmailConnect, EmailSync, AutomationRuleCreate, AutomationRuleUpdate,
    ResetRequest,
)
from automations import EMAIL_ACTIONS, process_new_emails, serialize_rule, serialize_run
from ollama import ollama_client, aclose as _ollama_aclose
from memory import memory_manager
from documents import document_manager
from research import research_agent
from intelligence import chat_intelligence, PLACEHOLDER_TITLE_RE

logger = logging.getLogger(__name__)
_email_sync_lock = threading.Lock()

# Fire-and-forget background work. asyncio holds only a weak reference to a task,
# so the handle must be kept alive or the task can be garbage-collected mid-flight
# and its exception never retrieved.
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro, *, name: str | None = None) -> None:
    """Schedule `coro` without blocking, keeping a strong reference until it finishes."""
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)

    def _done(t: asyncio.Task) -> None:
        _background_tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.warning("Background task %s failed: %s", t.get_name(), t.exception())

    task.add_done_callback(_done)


def _sync_and_process_email(db: Session, max_results: int, unread_only: bool) -> tuple[list[EmailDB], list[dict]]:
    """Run the single shared sync path; the lock prevents duplicate IMAP work."""
    with _email_sync_lock:
        new_emails = email_service.sync_inbox(db, max_results=max_results, unread_only=unread_only)
        runs = process_new_emails(db, new_emails)
        return new_emails, runs


def _background_email_sync_once() -> None:
    if not email_service.is_connected():
        return
    db = SessionLocal()
    try:
        new_emails, runs = _sync_and_process_email(db, EMAIL_AUTO_SYNC_MAX_RESULTS, False)
        logger.info("Background email sync completed: %d new email(s), %d automation run(s)", len(new_emails), len(runs))
    except Exception:
        logger.exception("Background email sync failed; it will be retried on the next interval")
    finally:
        db.close()


async def _auto_email_sync_loop() -> None:
    """Perform an immediate non-blocking sync, then continue at the configured interval."""
    while True:
        await asyncio.to_thread(_background_email_sync_once)
        await asyncio.sleep(EMAIL_AUTO_SYNC_INTERVAL_SECONDS)

# ── Email context helpers ──────────────────────────────────────────────────
_EMAIL_PATTERNS = [
    r'(check|show|get|read|fetch|list|look at|see|find|search|open|summari[sz]e|reply|respond|draft).{0,40}(email|gmail|mail|inbox|message)',
    r'(email|gmail|mail|inbox|message).{0,40}(check|show|get|read|fetch|list|recent|latest|new|unread|from)',
    r'(any|do i have|got any|have any|are there|were there).{0,30}(email|mail|message)',
    r'(what|which).{0,30}(email|mail|message|inbox)',
    r'(unread|unopened).{0,30}(email|mail|message)',
    r'(email|mail|message).{0,20}(unread|unopened|new|from)',
    r'emails?.{0,40}from',
    r'from.{0,40}emails?',
    r'\binbox\b',
    r'\bgmail\b',
]

# Follow-up references ("summarize the one from leetcode") that only make sense
# when emails were just shown — matched only if recent history listed emails.
_EMAIL_FOLLOWUP = _re.compile(
    r'\b(summari[sz]e|summary|reply|respond|draft|forward)\b'
    r'|\b(read|open)\s+(the|that|this|it|first|second|third|last|latest)\b'
    # "the one", "the google one", "that email", "the leetcode message", "first one"…
    r'|\b(the|that|this|first|second|third|fourth|last|latest)\s+(?:[a-z0-9]+\s+)?(one|email|message|mail)\b'
    r'|\bfrom\s+[a-z0-9._%+\-@]+',
    _re.I,
)

def _history_shows_emails(history) -> bool:
    """True if the conversation is in 'email mode' — a recent USER turn asked about
    email (deterministic, pattern-based), or an assistant turn listed emails. Used so
    short follow-ups like 'summarize the one from leetcode' resolve to email context."""
    if not history:
        return False
    for msg in reversed(history[-6:]):
        role = msg.get("role")
        text = msg.get("content") or ""
        if role == "user":
            m = text.lower()
            if any(_re.search(p, m) for p in _EMAIL_PATTERNS):
                return True
        elif role == "assistant":
            if "Subject:" in text and ("From:" in text or "Received:" in text):
                return True
    return False

def _is_email_query(message: str, history=None) -> bool:
    msg = message.lower()
    if any(_re.search(p, msg) for p in _EMAIL_PATTERNS):
        return True
    # A short follow-up referencing emails that were just listed.
    if _history_shows_emails(history) and _EMAIL_FOLLOWUP.search(msg):
        return True
    # Keep email context for natural continuations such as "or Google?" and
    # "what about Reddit?" after an inbox search.
    if _history_shows_emails(history) and _re.match(r"^(?:or|and|what about)\s+\S", msg.strip()):
        return True
    return False

def _extract_email_search_terms(message: str) -> dict:
    """Pull out useful filters from the natural language query."""
    msg = message.lower()
    result = {"sender": None, "subject_keywords": [], "unread_only": False, "limit": 5, "want_body": False}

    # unread intent
    if any(w in msg for w in ["unread", "new ", "haven't read", "not read"]):
        result["unread_only"] = True

    # Intent to read a specific email in full (summarize / reply / open / "what does it say")
    if any(w in msg for w in ["summari", "reply", "respond", "draft", "read the", "read that",
                              "open the", "open that", "what does", "what's in", "whats in", "tell me about"]):
        result["want_body"] = True
        result["limit"] = 3

    # "from X" sender hint
    from_match = _re.search(r'\bfrom\s+([a-zA-Z0-9._%+\-@]+)', msg)
    if from_match:
        result["sender"] = from_match.group(1).strip()

    # "the X email/one/message" → focus term (matched against sender or subject)
    if not result["sender"]:
        focus = _re.search(r'\bthe\s+([a-z0-9]{3,})\s+(?:email|one|message|mail)\b', msg)
        if focus and focus.group(1) not in ("first", "second", "third", "last", "latest", "next"):
            result["sender"] = focus.group(1).strip()

    # "about X" / "regarding X" subject keywords
    about_match = _re.search(r'\b(?:about|regarding|re:|subject)\s+["\']?([^"\',.?!]+)', msg)
    if about_match:
        result["subject_keywords"] = about_match.group(1).strip().split()

    # A concise continuation after an email query, for example "or google?",
    # is a topic search even though it contains no explicit email noun.
    continuation = _re.match(r"^(?:or|and|what about)\s+(.+?)[?!.,]*$", msg.strip())
    if continuation and not result["sender"] and not result["subject_keywords"]:
        result["subject_keywords"] = continuation.group(1).strip().split()

    # quantity hints
    num_match = _re.search(r'\b(\d+)\s+email', msg)
    if num_match:
        result["limit"] = min(int(num_match.group(1)), 20)
    elif any(w in msg for w in ["latest", "recent", "last"]):
        result["limit"] = 5
    elif "all" in msg:
        result["limit"] = 20

    return result


def _email_term_variants(term: str) -> set[str]:
    """Return conservative singular/plural variants for local email search."""
    term = term.strip().lower()
    if len(term) <= 3:
        return {term}
    variants = {term}
    if term.endswith("ies") and len(term) > 4:
        variants.add(term[:-3] + "y")
    elif term.endswith("s") and not term.endswith("ss"):
        variants.add(term[:-1])
    else:
        variants.add(term + "s")
    return {variant for variant in variants if variant}

def _build_email_context(db: Session, message: str) -> str:
    """Query locally synced EmailDB and return a formatted context block.

    Reading emails that have already been synced must work even while the IMAP
    connection is offline or has not been restored after a server restart.
    """

    filters = _extract_email_search_terms(message)
    q = db.query(EmailDB)

    if filters["unread_only"]:
        q = q.filter(EmailDB.is_unread == True)
    if filters["sender"]:
        # Match the term against the sender OR the subject (covers "from leetcode"
        # as well as "the puzzle one").
        like = f"%{filters['sender']}%"
        q = q.filter(
            EmailDB.sender.ilike(like) | EmailDB.subject.ilike(like) |
            EmailDB.snippet.ilike(like) | EmailDB.body.ilike(like)
        )
    if filters["subject_keywords"]:
        for kw in filters["subject_keywords"][:2]:
            variants = _email_term_variants(kw)
            q = q.filter(or_(*[
                EmailDB.sender.ilike(f"%{term}%") |
                EmailDB.subject.ilike(f"%{term}%") |
                EmailDB.snippet.ilike(f"%{term}%") |
                EmailDB.body.ilike(f"%{term}%")
                for term in variants
            ]))

    emails = q.order_by(EmailDB.received_at.desc()).limit(filters["limit"]).all()

    if not emails:
        qualifier = "unread " if filters["unread_only"] else ""
        return f"[Gmail] No {qualifier}emails found matching that query."

    # Include the full (trimmed) body when the user wants to read/summarize a
    # specific email, or when the query narrowed to a single message.
    include_body = filters["want_body"] or len(emails) == 1

    lines = [f"[Gmail] {len(emails)} email(s) retrieved:\n"]
    for i, e in enumerate(emails, 1):
        unread_marker = " (unread)" if e.is_unread else ""
        received = e.received_at.strftime("%b %d, %I:%M %p") if e.received_at else "unknown date"
        block = (
            f"{i}. From: {e.sender}{unread_marker}\n"
            f"   Subject: {e.subject or '(no subject)'}\n"
            f"   Received: {received}\n"
        )
        if include_body and (e.body or "").strip():
            body = _re.sub(r"[ \t]+", " ", e.body).strip()[:1800]
            block += f"   Full message:\n{body}\n"
        else:
            block += f"   Preview: {(e.snippet or '')[:200]}\n"
        lines.append(block)
    return "\n".join(lines)

def _format_email_listing_response(email_context: str) -> str:
    """Turn already-retrieved inbox metadata into a reliable, model-free reply."""
    if email_context.startswith("[Gmail] "):
        email_context = email_context[len("[Gmail] "):]
    return f"Here are the matching emails from your local inbox:\n\n{email_context}"


async def ensure_embedding_model_present():
    """Verify that nomic-embed-text is installed. If not, auto-pull in the background."""
    emb_model = "nomic-embed-text"
    try:
        models = await ollama_client.list_models()
        is_installed = any(
            m["name"] == emb_model or m["name"].startswith(f"{emb_model}:")
            for m in models
        )
        if not is_installed:
            logger.warning("Required embedding model '%s' is not installed.", emb_model)
            success = await ollama_client.pull_model(emb_model)
            if success:
                logger.info("Embedding model '%s' is ready for search/memory.", emb_model)
            else:
                logger.error("Auto-pull for '%s' failed. Please run 'ollama pull %s' manually.", emb_model, emb_model)
        else:
            logger.info("Embedding model '%s' is already installed.", emb_model)
    except Exception as e:
        logger.error("Failed checking/pulling embedding model: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise the database on startup (not at import time).
    init_db()
    health = await ollama_client.check_health()
    if health:
        try:
            await ollama_client.get_model()
        except Exception as e:
            logger.error("Could not select Ollama model: %s", e)
        logger.info("Connected to Ollama at %s", ollama_client.host)
        # Run embedding model validation asynchronously in background.
        asyncio.create_task(ensure_embedding_model_present())
    else:
        logger.error("Could not connect to Ollama at %s", ollama_client.host)
    auto_sync_task = None
    if EMAIL_AUTO_SYNC:
        auto_sync_task = asyncio.create_task(_auto_email_sync_loop(), name="mindbase-email-auto-sync")
        logger.info("Background email auto-sync enabled (every %d seconds)", EMAIL_AUTO_SYNC_INTERVAL_SECONDS)
    yield
    if auto_sync_task:
        auto_sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await auto_sync_task
    # Shutdown: close the shared pooled Ollama HTTP client so its keep-alive
    # connections are released cleanly on reload/exit.
    try:
        await _ollama_aclose()
    except Exception as e:
        logger.warning("Error closing Ollama client on shutdown: %s", e)


app = FastAPI(title="Mindbase AI Workspace", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Email context helpers ────────────────────────────────────────────────────

_EMAIL_PATTERNS = [
    # Original patterns kept for backward compatibility
    r'(check|show|get|read|fetch|list|look at|see|find|search|open|summari[sz]e|reply|respond|draft).{0,40}(email|gmail|mail|inbox|message)',
    r'(email|gmail|mail|inbox|message).{0,40}(check|show|get|read|fetch|list|recent|latest|new|unread|from)',
    r'(any|do i have|got any|have any|are there|were there).{0,30}(email|mail|message)',
    r'(what|which).{0,30}(email|mail|message|inbox)',
    r'(unread|unopened).{0,30}(email|mail|message)',
    r'(email|mail|message).{0,20}(unread|unopened|new|from)',
    r'emails?.{0,40}from',
    r'from.{0,40}emails?',
    r'\binbox\b',
    r'\bgmail\b',

    # ENHANCED PATTERNS for natural language understanding
    # Phrases that start with exploratory language
    r'(tell\s+me\s+about|describe|explain|what.?s?\s+the?\s+status\s+of|how\s+many|show\s+me\s+what.?s?\s+in|look\s+at\s+my|see\s+if\s+I\s+have|did\s+I\s+get|have\s+I\s+received|any\s+(new\s+)?|are\s+there\s+|what\s+emails\s+do\s+I\s+have|do\s+I\s+have\s+any\s+email|got\s+any\s+email|no\s+new\s+email)\b.*\b(email|emails?|mail|messages?|inbox|gmail)\b',
    r'tell\s+me\s+.*\b(email|emails?|mail|messages?|inbox|gmail)\b',
    r'tell\s+me\s+.*\b(latest|recent|today.?s?|yesterday.?s?|this\s+morning.?s?|this\s+afternoon.?s?|this\s+evening.?s?|this\s+week.?s?|unread\s+|new\s+|pending\s+|important\s+|urgent\s+)\b.*\b(email|emails?|mail|messages?|inbox|gmail)\b',

    # Phrases that end with exploratory language
    r'\b(email|emails?|mail|messages?|inbox|gmail).*\b(tell\s+me\s+about|describe|explain|what.?s?\s+the?\s+status\s+of|how\s+many|show\s+me\s+what.?s?\s+in|look\s+at\s+my|see\s+if\s+I\s+have|did\s+I\s+get|have\s+I\s+received|any\s+(new\s+)?|are\s+there\s+|what\s+emails\s+do\s+I\s+have|do\s+I\s+have\s+any\s+email|got\s+any\s+email|no\s+new\s+email)\b',

    # Time-based email queries (more flexible)
    r'\b(latest|recent|today.?s?|yesterday.?s?|this\s+morning.?s?|this\s+afternoon.?s?|this\s+evening.?s?|this\s+week.?s?|unread\s+|new\s+|pending\s+|important\s+|urgent\s+)\b.*\b(email|emails?|mail|messages?|inbox|gmail)\b',
    r'\b(email|emails?|mail|messages?|inbox|gmail).*\b(latest|recent|today.?s?|yesterday.?s?|this\s+morning.?s?|this\s+afternoon.?s?|this\s+evening.?s?|this\s+week.?s?|unread\s+|new\s+|pending\s+|important\s+|urgent\s+)\b',

    # Sender-focused queries
    r'\b(from\s+|sender\s+|who\s+is\s+from\s+|messages\s+from\s+|email\s+from\s+|received\s+from\s+|got\s+email\s+from)\b.*\b([a-zA-Z0-9._%+\-@]+)',
    r'\b([a-zA-Z0-9._%+\-@]+).*\b(from\s+|sender\s+|who\s+is\s+from\s+|messages\s+from\s+|email\s+from\s+|received\s+from\s+|got\s+email\s+from)\b',

    # Content/topic-focused queries
    r'\b(about\s+|regarding\s+|concerning\s+|topic\s+|subject\s+|regarding\s+|re:)\s*.*?\b(email|emails?|mail|messages?|inbox|gmail)\b',
    r'\b(email|emails?|mail|messages?|inbox|gmail).*\b(about\s+|regarding\s+|concerning\s+|topic\s+|subject\s+|regarding\s+|re:)\s*.*?\b',

    # Ordinal-focused email queries
    r'\bthe\s+\d+(st|nd|rd|th)\s+email\b.*\b(email|emails?|mail|messages?|inbox|gmail)\b',
    r'\b(email|emails?|mail|messages?|inbox|gmail).*\bthe\s+\d+(st|nd|rd|th)\s+email\b',


# Action-oriented email requests
    r'\b(read\s+the\s+|open\s+the\s+|check\s+the\s+|look\s+at\s+the\s+|see\s+the\s+|what.?s?\s+in\s+the\s+|content\s+of\s+|meaning\s+of\s+meaning\s+of\s+|meaning\s+of\s+)\s+(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+)?\s*(email|message|mail)\b',
    r'\b(email|message|mail)\s+(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+)?\s*(read\s+the\s+|open\s+the\s+|check\s+the\s+|look\s+at\s+the\s+|see\s+the\s+|what.?s?\s+in\s+the\s+|content\s+of\s+|meaning\s+of\s+|meaning\s+of\s+)\b',

    # Summary requests
    r'\b(summarize\s+|summary\s+of\s+|give\s+me\s+a\s+summary\s+of\s+|brief\s+me\s+on\s+|quick\s+overview\s+of\s+|summarize\s+this\s+|summarize\s+the\s+)(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+)?\s*(email|message|mail)\b',
    r'\b(email|message|mail)\s+(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+)?\s*(summarize\s+|summary\s+of\s+|give\s+me\s+a\s+summary\s+of\s+|brief\s+me\s+on\s+|quick\s+overview\s+of\s+|summarize\s+this\s+|summarize\s+the\s+)\b',
]

# Follow-up references ("summarize the one from leetcode") that only make sense
# when emails were just shown — matched only if recent history listed emails.
_EMAIL_FOLLOWUP = _re.compile(
    r'\b(summari[sz]e|summary|reply|respond|draft|forward)\b'
    r'|\b(read|open)\s+(the|that|this|it|first|second|third|last|latest)\b'
    # "the one", "the google one", "that email", "the leetcode message", "first one"…
    r'|\b(the|that|this|first|second|third|fourth|last|latest)\s+(?:[a-z0-9]+\s+)?(one|email|message|mail)\b'
    r'|\bfrom\s+[a-z0-9._%+\-@]+'
    # Enhanced follow-up patterns
    r'|\b(what\s+did\s+it\s+say|what\s+does\s+it\s+say|content\s+of|meaning\s+of|read\s+the\s+|open\s+the\s+|tell\s+me\s+about\s+|describe\s+|what.?s?\s+in\s+)\s+(the|that|this|it|first|second|third|last|latest|one|null)\s*(email|message|mail)\b'
    r'|\b(summarize\s+|summary\s+of\s+|give\s+me\s+a\s+summary\s+of\s+|brief\s+me\s+on\s+|quick\s+overview\s+of\s+)\s+(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+|one\s+|null\s*)\s*(email|message|mail)\b'
    r'|\b(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+|one\s+|null\s*)\s*(email|message|mail)\s*(summarize\s+|summary\s+of\s+|give\s+me\s+a\s+summary\s+of\s+|brief\s+me\s+on\s+|quick\s+overview\s+of\s+|what\s+did\s+it\s+say|what\s+does\s+it\s+say|content\s+of|meaning\s+of|read\s+the\s+|open\s+the\s+|tell\s+me\s+about\s+|describe\s+|what.?s?\s+in\s+)\b',
    _re.I,
)

def _history_shows_emails(history) -> bool:
    """True if the conversation is in 'email mode' — a recent USER turn asked about
    email (deterministic, pattern-based), or an assistant turn listed emails. Used so
    short follow-ups like 'summarize the one from leetcode' resolve to email context."""
    if not history:
        return False
    for msg in reversed(history[-6:]):
        role = msg.get("role")
        text = msg.get("content") or ""
        if role == "user":
            m = text.lower()
            if any(_re.search(p, m) for p in _EMAIL_PATTERNS):
                return True
        elif role == "assistant":
            if "Subject:" in text and ("From:" in text or "Received:" in text):
                return True
    return False

def _is_email_query(message: str, history=None) -> bool:
    msg = message.lower()
    if any(_re.search(p, msg) for p in _EMAIL_PATTERNS):
        return True
    # A short follow-up referencing emails that were just listed.
    if _history_shows_emails(history) and _EMAIL_FOLLOWUP.search(msg):
        return True
    if _history_shows_emails(history) and _re.match(r"^(?:or|and|what about)\s+\S", msg.strip()):
        return True
    return False

def _extract_email_search_terms(message: str) -> dict:
    """Pull out useful filters from the natural language query."""
    msg = message.lower()
    result = {"sender": None, "subject_keywords": [], "unread_only": False, "limit": 5, "want_body": False}

    # unread intent
    if any(w in msg for w in ["unread", "new ", "haven't read", "not read"]):
        result["unread_only"] = True

    # Intent to read a specific email in full (summarize / reply / open / "what does it say")
    if any(w in msg for w in ["summari", "reply", "respond", "draft", "read the", "read that",
                              "open the", "open that", "what does", "what's in", "whats in", "tell me about"]):
        result["want_body"] = True
        result["limit"] = 3

    # "from X" sender hint
    from_match = _re.search(r'\bfrom\s+([a-zA-Z0-9._%+\-@]+)', msg)
    if from_match:
        result["sender"] = from_match.group(1).strip()

    # "the X email/one/message" → focus term (matched against sender or subject)
    if not result["sender"]:
        focus = _re.search(r'\bthe\s+([a-z0-9]{3,})\s+(?:email|one|message|mail)\b', msg)
        if focus and focus.group(1) not in ("first", "second", "third", "last", "latest", "next"):
            result["sender"] = focus.group(1).strip()

    # "about X" / "regarding X" subject keywords
    about_match = _re.search(r'\b(?:about|regarding|re:|subject)\s+["\']?([^"\',.?!]+)', msg)
    if about_match:
        result["subject_keywords"] = about_match.group(1).strip().split()

    continuation = _re.match(r"^(?:or|and|what about)\s+(.+?)[?!.,]*$", msg.strip())
    if continuation and not result["sender"] and not result["subject_keywords"]:
        result["subject_keywords"] = continuation.group(1).strip().split()

    # quantity hints
    num_match = _re.search(r'\b(\d+)\s+email', msg)
    if num_match:
        result["limit"] = min(int(num_match.group(1)), 20)
    elif any(w in msg for w in ["latest", "recent", "last"]):
        result["limit"] = 5
    elif "all" in msg:
        result["limit"] = 20

    return result

def _build_email_context(db: Session, message: str) -> str:
    """Query locally synced EmailDB and return a formatted context block.

    Reading emails that have already been synced must work even while the IMAP
    connection is offline or has not been restored after a server restart.
    """

    filters = _extract_email_search_terms(message)
    q = db.query(EmailDB)

    if filters["unread_only"]:
        q = q.filter(EmailDB.is_unread == True)
    if filters["sender"]:
        # Match the term against the sender OR the subject (covers "from leetcode"
        # as well as "the puzzle one").
        like = f"%{filters['sender']}%"
        q = q.filter(
            EmailDB.sender.ilike(like) | EmailDB.subject.ilike(like) |
            EmailDB.snippet.ilike(like) | EmailDB.body.ilike(like)
        )
    if filters["subject_keywords"]:
        for kw in filters["subject_keywords"][:2]:
            variants = _email_term_variants(kw)
            q = q.filter(or_(*[
                EmailDB.sender.ilike(f"%{term}%") |
                EmailDB.subject.ilike(f"%{term}%") |
                EmailDB.snippet.ilike(f"%{term}%") |
                EmailDB.body.ilike(f"%{term}%")
                for term in variants
            ]))

    emails = q.order_by(EmailDB.received_at.desc()).limit(filters["limit"]).all()

    if not emails:
        qualifier = "unread " if filters["unread_only"] else ""
        return f"[Gmail] No {qualifier}emails found matching that query."

    # Include the full (trimmed) body when the user wants to read/summarize a
    # specific email, or when the query narrowed to a single message.
    include_body = filters["want_body"] or len(emails) == 1

    lines = [f"[Gmail] {len(emails)} email(s) retrieved:\n"]
    for i, e in enumerate(emails, 1):
        unread_marker = " (unread)" if e.is_unread else ""
        received = e.received_at.strftime("%b %d, %I:%M %p") if e.received_at else "unknown date"
        block = (
            f"{i}. From: {e.sender}{unread_marker}\n"
            f"   Subject: {e.subject or '(no subject)'}\n"
            f"   Received: {received}\n"
        )
        if include_body and (e.body or "").strip():
            body = _re.sub(r"[ \t]+", " ", e.body).strip()[:1800]
            block += f"   Full message:\n{body}\n"
        else:
            block += f"   Preview: {(e.snippet or '')[:200]}\n"
        lines.append(block)
    return "\n".join(lines)


def _format_email_listing_response(email_context: str) -> str:
    """Turn already-retrieved inbox metadata into a reliable, model-free reply."""
    if email_context.startswith("[Gmail] "):
        email_context = email_context[len("[Gmail] "):]
    return f"Here are the matching emails from your local inbox:\n\n{email_context}"

@app.get("/api/health")
async def health_check():
    ollama_health = await ollama_client.check_health()
    return {
        "status": "healthy",
        "ollama": "connected" if ollama_health else "disconnected",
        "current_model": ollama_client.current_model
    }

@app.get("/api/ollama/models")
async def get_models():
    models = await ollama_client.list_models()
    return {"models": models}

@app.post("/api/ollama/switch")
async def switch_model(data: ModelSwitchRequest):
    success = await ollama_client.set_model(data.model)
    if success:
        return {"status": "success", "model": data.model}
    else:
        raise HTTPException(status_code=404, detail="Model not found")

@app.post("/api/chat/conversations")
def create_conversation(data: ConversationCreate, db: Session = Depends(get_db)):
    conv = ConversationDB(title=data.title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at
    }

@app.get("/api/chat/conversations")
def list_conversations(db: Session = Depends(get_db)):
    conversations = db.query(ConversationDB).order_by(ConversationDB.updated_at.desc()).all()
    result = []
    for conv in conversations:
        result.append({
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "message_count": len(conv.messages)
        })
    return result

@app.get("/api/chat/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conv = db.query(ConversationDB).filter(ConversationDB.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = []
    for msg in conv.messages:
        messages.append({
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "model": msg.model,
            "created_at": msg.created_at
        })

    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "messages": messages
    }

@app.post("/api/chat/messages")
async def send_message(request: ChatRequest, db: Session = Depends(get_db)):
    conv = db.query(ConversationDB).filter(ConversationDB.id == request.conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_msg = MessageDB(
        conversation_id=request.conversation_id,
        role="user",
        content=request.message,
        model=request.model or ollama_client.current_model
    )
    db.add(user_msg)
    db.commit()

    history = []
    for msg in conv.messages:
        if msg.id != user_msg.id:
            history.append({"role": msg.role, "content": msg.content})
    history.append({"role": "user", "content": request.message})

    # Check email intent first — if this is an email query, skip task_manager
    # so it doesn't create a task called "Email Check" instead of fetching emails.
    email_context_block = ""
    direct_email_response = ""
    if _is_email_query(request.message, history):
        email_context_block = _build_email_context(db, request.message)
        actions_taken = []
        if email_context_block:
            actions_taken.append({"type": "email_context", "summary": "Retrieved emails from Gmail"})
            # Listing headers/previews does not need an LLM round-trip. Returning the
            # locally retrieved data directly is faster and avoids competing model
            # requests while the inbox is being checked. Reading, summarizing, and
            # drafting still use the model below.
            if not _extract_email_search_terms(request.message)["want_body"]:
                direct_email_response = _format_email_listing_response(email_context_block)

    if direct_email_response:
        # Simple inbox listings are completely local: avoid model discovery and
        # generic context gathering so the SSE response starts right away.
        model = "local-inbox"
        intent = "email"
        context_sources = ["emails"]
        messages = []
    else:
        try:
            model = await ollama_client.get_model(request.model)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

    if not _is_email_query(request.message, history):
        actions_taken = await task_manager.process_with_history(
            request.message, history, db, model=model
        )

    if not direct_email_response:
        prepared = await chat_intelligence.prepare_chat(
            user_message=request.message,
            history=history,
            db=db,
            model=model,
            agent_prompt=request.agent_prompt,
            temperature=request.temperature,
            actions_taken=actions_taken,
            include_memory=request.include_memory,
        )
        messages = prepared.messages
        intent = prepared.intent
        context_sources = prepared.context_sources
    gen_temperature = request.temperature

    # For email queries, prepend the Gmail context as a high-priority system message
    # so the LLM reads it instead of relying on the schedule/task context injected by
    # chat_intelligence. Insert right after the first system message (index 0) if one
    # exists, otherwise prepend to the front.
    if email_context_block and not direct_email_response:
        email_sys = {
            "role": "system",
            "content": (
                f"The user is asking about their emails. Here is their current Gmail inbox data:\n\n"
                f"{email_context_block}\n\n"
                f"Use ONLY this data to answer. Do not mention tasks, calendar events, or anything "
                f"unrelated to email unless the user asks."
            )
        }
        # Find first system message and insert after it, or prepend
        sys_idx = next((i for i, m in enumerate(messages) if m.get("role") == "system"), None)
        if sys_idx is not None:
            messages.insert(sys_idx + 1, email_sys)
        else:
            messages.insert(0, email_sys)
        logger.debug("Injected email system message at position %s", (sys_idx + 1) if sys_idx is not None else 0)

    async def generate():
        response_text = ""
        meta = {
            "intent": intent,
            "context": context_sources,
            "actions": actions_taken,
        }
        yield f"data: {json.dumps({'meta': meta})}\n\n"

        if direct_email_response:
            response_text = direct_email_response
            yield f"data: {json.dumps({'chunk': response_text})}\n\n"
        else:
            async for chunk in ollama_client.stream_generate(
                model, messages, temperature=gen_temperature, num_predict=request.max_tokens
            ):
                response_text += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        assistant_msg = MessageDB(
            conversation_id=request.conversation_id,
            role="assistant",
            content=response_text,
            model=model
        )
        db.add(assistant_msg)
        conv.updated_at = datetime.utcnow()
        db.commit()

        # Ordered history, loaded once and shared by auto-titling and memory extraction.
        try:
            ordered = [
                {"role": m.role, "content": m.content}
                for m in sorted(conv.messages, key=lambda x: x.created_at)
            ]
        except Exception as e:
            logger.error("Could not load conversation history: %s", e)
            ordered = []

        # Auto-title once there is a real exchange to summarize. Fire-and-forget so it
        # never delays the `done` frame; background_title opens its own DB session.
        if ordered and PLACEHOLDER_TITLE_RE.match(conv.title or ""):
            _spawn_background(
                chat_intelligence.background_title(request.conversation_id, ordered, model),
                name=f"auto-title:{request.conversation_id}",
            )

        # Auto-extract memory from conversation, unless the user turned it off in
        # Settings ("Auto-extract from chat").
        if request.auto_memory:
            try:
                await memory_manager.auto_extract_memory_from_chat(request.conversation_id, ordered[-6:])
            except Exception as e:
                logger.error("Memory extraction error: %s", e)

        yield f"data: {json.dumps({'done': True, 'message_id': assistant_msg.id})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.delete("/api/chat/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conv = db.query(ConversationDB).filter(ConversationDB.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conv)
    db.commit()
    return {"status": "deleted"}

@app.put("/api/chat/conversations/{conversation_id}")
def update_conversation(conversation_id: str, data: ConversationUpdate, db: Session = Depends(get_db)):
    conv = db.query(ConversationDB).filter(ConversationDB.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    updates = data.model_dump(exclude_unset=True)
    if "title" in updates:
        conv.title = updates["title"]

    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conv)

    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at
    }

# Memory endpoints
@app.post("/api/memory/create")
async def create_memory(data: MemoryCreate):
    memory = await memory_manager.create_memory(data.content, data.type, data.tags or [])
    return memory

@app.get("/api/memory/list")
async def list_memories():
    memories = await memory_manager.get_all_memories()
    return {"memories": memories, "count": len(memories)}

@app.get("/api/memory/list/{memory_type}")
async def list_memories_by_type(memory_type: str):
    memories = await memory_manager.get_memories_by_type(memory_type)
    return {"memories": memories, "count": len(memories), "type": memory_type}

@app.post("/api/memory/search")
async def search_memories(data: MemorySearch):
    memories = await memory_manager.search_memories(data.query, data.type, limit=10)
    return {"memories": memories, "count": len(memories), "query": data.query}

@app.put("/api/memory/{memory_id}")
async def update_memory(memory_id: str, data: MemoryUpdate):
    updated = await memory_manager.update_memory(memory_id, data.content, data.tags, data.metadata)
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found")

    return updated

@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    success = await memory_manager.delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"status": "deleted", "id": memory_id}

# Notes endpoints
def serialize_note(note: NoteDB):
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "tags": note.tags.split(",") if note.tags else [],
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat()
    }

async def sync_note_to_memory(note: NoteDB):
    tags = note.tags.split(",") if note.tags else []
    try:
        await memory_manager.upsert_note_memory(note.id, note.title, note.content, tags)
    except Exception as e:
        logger.error("Error syncing note to memory: %s", e)

@app.post("/api/notes")
async def create_note(data: NoteCreate, db: Session = Depends(get_db)):
    note = NoteDB(title=data.title, content=data.content, tags=",".join(data.tags or []))
    db.add(note)
    db.commit()
    db.refresh(note)

    await sync_note_to_memory(note)
    return serialize_note(note)

@app.get("/api/notes")
def list_notes(db: Session = Depends(get_db)):
    notes = db.query(NoteDB).order_by(NoteDB.updated_at.desc()).all()
    return {
        "notes": [{
            "id": n.id,
            "title": n.title,
            "content": n.content[:100] + "..." if len(n.content) > 100 else n.content,
            "tags": n.tags.split(",") if n.tags else [],
            "created_at": n.created_at.isoformat(),
            "updated_at": n.updated_at.isoformat()
        } for n in notes],
        "count": len(notes)
    }

@app.get("/api/notes/{note_id}")
def get_note(note_id: str, db: Session = Depends(get_db)):
    note = db.query(NoteDB).filter(NoteDB.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    return serialize_note(note)

@app.put("/api/notes/{note_id}")
async def update_note(note_id: str, data: NoteUpdate, db: Session = Depends(get_db)):
    note = db.query(NoteDB).filter(NoteDB.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    updates = data.model_dump(exclude_unset=True)
    if "title" in updates:
        note.title = updates["title"]
    if "content" in updates:
        note.content = updates["content"]
    if "tags" in updates and updates["tags"] is not None:
        note.tags = ",".join(updates["tags"])

    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)

    await sync_note_to_memory(note)
    return serialize_note(note)

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: str, db: Session = Depends(get_db)):
    note = db.query(NoteDB).filter(NoteDB.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    db.delete(note)
    db.commit()
    await memory_manager.delete_note_memory(note_id)
    return {"status": "deleted", "id": note_id}

# Tasks endpoints
@app.post("/api/tasks")
def create_task(data: TaskCreate, db: Session = Depends(get_db)):
    due = _parse_date_string(data.due_date) if data.due_date else None

    task = task_manager.create_task(
        db,
        data.title,
        description=data.description,
        status=data.status,
        priority=data.priority,
        due_date=due,
        tags=data.tags or [],
    )
    return serialize_task(task)

@app.get("/api/tasks")
def list_tasks(db: Session = Depends(get_db)):
    tasks = db.query(TaskDB).order_by(TaskDB.due_date).all()
    return {
        "tasks": [serialize_task(t) for t in tasks],
        "count": len(tasks),
    }

@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "tags": task.tags.split(",") if task.tags else [],
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat()
    }

@app.put("/api/tasks/{task_id}")
def update_task(task_id: str, data: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updates = data.model_dump(exclude_unset=True)
    if "title" in updates:
        task.title = updates["title"]
    if "description" in updates:
        task.description = updates["description"]
    if "status" in updates:
        task.status = updates["status"]
    if "priority" in updates:
        task.priority = updates["priority"]
    if "tags" in updates and updates["tags"] is not None:
        task.tags = ",".join(updates["tags"])
    if "due_date" in updates:
        task.due_date = _parse_date_string(updates["due_date"]) if updates["due_date"] else None

    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)

    return serialize_task(task)

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return {"status": "deleted", "id": task_id}


# Calendar endpoints
@app.get("/api/calendar")
def get_calendar(
    start: str,
    end: str,
    db: Session = Depends(get_db),
):
    start_dt = _parse_date_string(start)
    end_dt = _parse_date_string(end)
    if not start_dt or not end_dt:
        raise HTTPException(status_code=400, detail="Valid start and end ISO dates required")

    items = task_manager.get_calendar_items(db, start_dt, end_dt, include_completed_tasks=True)
    return {"items": items, "count": len(items)}


@app.post("/api/calendar/events")
def create_calendar_event(data: CalendarEventCreate, db: Session = Depends(get_db)):
    start = _parse_date_string(data.start or data.start_at or "")
    if not data.title or not start:
        raise HTTPException(status_code=400, detail="title and start are required")

    end = _parse_date_string(data.end or data.end_at or "")
    event = task_manager.create_event(
        db,
        data.title,
        start,
        end,
        description=data.description,
        all_day=data.all_day,
        location=data.location,
        color=data.color,
    )
    return serialize_event(event)


@app.put("/api/calendar/events/{event_id}")
def update_calendar_event(event_id: str, data: CalendarEventUpdate, db: Session = Depends(get_db)):
    event = db.query(CalendarEventDB).filter(CalendarEventDB.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    updates = data.model_dump(exclude_unset=True)
    if "title" in updates:
        event.title = updates["title"]
    if "description" in updates:
        event.description = updates["description"]
    if "start" in updates or "start_at" in updates:
        parsed = _parse_date_string(updates.get("start") or updates.get("start_at"))
        if parsed:
            event.start_at = parsed
    if "end" in updates or "end_at" in updates:
        parsed = _parse_date_string(updates.get("end") or updates.get("end_at"))
        if parsed:
            event.end_at = parsed
    if "all_day" in updates:
        event.all_day = 1 if updates["all_day"] else 0
    if "location" in updates:
        event.location = updates["location"]
    if "color" in updates:
        event.color = updates["color"]

    event.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(event)
    return serialize_event(event)


@app.delete("/api/calendar/events/{event_id}")
def delete_calendar_event(event_id: str, db: Session = Depends(get_db)):
    event = db.query(CalendarEventDB).filter(CalendarEventDB.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()
    return {"status": "deleted", "id": event_id}


# Research endpoints
@app.post("/api/research")
async def start_research(data: ResearchRequest, db: Session = Depends(get_db)):
    query = data.query
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    async def generate():
        async for update in research_agent.research(query):
            if update.get("type") == "report":
                try:
                    note_id = await research_agent.save_report_to_note(update, db)
                    update["note_id"] = note_id
                    update["saved_to_notes"] = True
                except Exception as e:
                    update["saved_to_notes"] = False
                    update["save_error"] = str(e)
            yield f"data: {json.dumps(update)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/research/save")
async def save_research_report(data: ResearchSaveRequest, db: Session = Depends(get_db)):
    report = data.report
    if not report:
        raise HTTPException(status_code=400, detail="Report is required")

    existing_note_id = report.get("note_id")
    if existing_note_id:
        return {"status": "already_saved", "note_id": existing_note_id}

    note_id = await research_agent.save_report_to_note(report, db)
    return {"status": "saved", "note_id": note_id}

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    try:
        content = await file.read()
        result = await document_manager.upload_document(file.filename, content)

        if not result:
            raise HTTPException(status_code=400, detail="Failed to process document")

        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/documents")
async def list_documents():
    docs = await document_manager.list_documents()
    return {"documents": docs, "count": len(docs)}

@app.post("/api/documents/{document_id}/ask")
async def ask_document(document_id: str, data: DocumentAsk):
    query = data.query
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    result = await document_manager.ask_document(query, document_id)
    return result

@app.post("/api/documents/{document_id}/summary")
async def summarize_document(document_id: str):
    summary = await document_manager.summarize_document(document_id)
    if not summary:
        raise HTTPException(status_code=400, detail="Failed to summarize document")

    return {"summary": summary}

@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: str):
    success = document_manager.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted", "id": document_id}


# ── Email endpoints (IMAP) ───────────────────────────────────────────────────
@app.get("/api/email/status")
def email_status():
    return {"connected": email_service.is_connected(), "email": email_service.account_email()}

@app.post("/api/email/connect")
async def email_connect(data: EmailConnect):
    address = (data.email or "").strip()
    password = (data.app_password or "").strip()
    host = (data.host or "").strip()
    if not address or not password:
        raise HTTPException(status_code=400, detail="Email and app password are required.")
    try:
        email_service.connect(address, password, host=host)
    except Exception as e:
        # imaplib raises imaplib.IMAP4.error on bad credentials; surface a clean message.
        msg = str(e) or "Could not sign in. Check the address and app password."
        if "AUTHENTICATIONFAILED" in msg.upper() or "Invalid credentials" in msg:
            msg = "Sign-in failed. Make sure you used an app password, not your normal password."
        raise HTTPException(status_code=401, detail=msg)
    if EMAIL_AUTO_SYNC:
        _spawn_background(asyncio.to_thread(_background_email_sync_once), name="email-first-sync")
    return {"connected": True, "email": email_service.account_email()}

@app.post("/api/email/disconnect")
def email_disconnect():
    email_service.disconnect()
    return {"status": "disconnected"}

@app.post("/api/email/sync")
def sync_email(data: Optional[EmailSync] = None, db: Session = Depends(get_db)):
    if not email_service.is_connected():
        raise HTTPException(status_code=401, detail="Email not connected")
    # The body is optional (the client may POST empty), so fall back to defaults.
    payload = data or EmailSync()
    max_results = payload.max_results
    unread_only = payload.unread_only
    try:
        new_emails, runs = _sync_and_process_email(db, max_results=max_results, unread_only=unread_only)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach your mail server: {e}")
    return {"new_count": len(new_emails), "emails": [serialize_email(e) for e in new_emails], "automation_runs": runs}


# ── Automation endpoints ────────────────────────────────────────────────────
@app.get("/api/automations")
def list_automations(db: Session = Depends(get_db)):
    rules = db.query(AutomationRuleDB).order_by(AutomationRuleDB.created_at.desc()).all()
    return {"automations": [serialize_rule(rule) for rule in rules]}

@app.post("/api/automations", status_code=201)
def create_automation(data: AutomationRuleCreate, db: Session = Depends(get_db)):
    if data.trigger != "email":
        raise HTTPException(status_code=422, detail="Only email triggers are supported currently.")
    invalid = set(data.actions) - EMAIL_ACTIONS
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported email actions: {', '.join(sorted(invalid))}")
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Automation name cannot be blank.")
    rule = AutomationRuleDB(name=name, trigger=data.trigger, condition=data.condition.strip(), actions=json.dumps(data.actions), details=data.details.strip(), enabled=data.enabled)
    db.add(rule); db.commit(); db.refresh(rule)
    return serialize_rule(rule)

@app.put("/api/automations/{rule_id}")
def update_automation(rule_id: str, data: AutomationRuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(AutomationRuleDB).filter_by(id=rule_id).first()
    if not rule: raise HTTPException(status_code=404, detail="Automation not found")
    update = data.model_dump(exclude_unset=True)
    if "name" in update and not update["name"].strip():
        raise HTTPException(status_code=422, detail="Automation name cannot be blank.")
    if "actions" in update:
        invalid = set(update["actions"]) - EMAIL_ACTIONS
        if not update["actions"] or invalid: raise HTTPException(status_code=422, detail="Provide supported automation actions.")
        rule.actions = json.dumps(update.pop("actions"))
    for field in ("name", "condition", "details", "enabled"):
        if field in update: setattr(rule, field, update[field].strip() if isinstance(update[field], str) else update[field])
    db.commit(); db.refresh(rule)
    return serialize_rule(rule)

@app.delete("/api/automations/{rule_id}")
def delete_automation(rule_id: str, db: Session = Depends(get_db)):
    rule = db.query(AutomationRuleDB).filter_by(id=rule_id).first()
    if not rule: raise HTTPException(status_code=404, detail="Automation not found")
    db.delete(rule); db.commit()
    return {"status": "deleted", "id": rule_id}

@app.get("/api/automations/done")
def list_completed_automations(limit: int = 50, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    runs = db.query(AutomationRunDB).order_by(AutomationRunDB.created_at.desc()).limit(limit).all()
    return {"runs": [serialize_run(run, db) for run in runs], "count": len(runs)}

@app.get("/api/automations/attachments/{attachment_id}/download")
def download_automation_attachment(attachment_id: str, db: Session = Depends(get_db)):
    attachment = db.query(EmailAttachmentDB).filter_by(id=attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = (ATTACHMENTS_DIR / attachment.stored_name).resolve()
    if path.parent != ATTACHMENTS_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file is unavailable")
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.filename)

@app.get("/api/email/inbox")
def list_inbox(unread_only: bool = False, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(EmailDB)
    if unread_only:
        q = q.filter(EmailDB.is_unread == True)
    emails = q.order_by(EmailDB.received_at.desc()).limit(limit).all()
    return {"emails": [serialize_email(e) for e in emails], "count": len(emails)}

@app.get("/api/email/unread-count")
def unread_email_count(db: Session = Depends(get_db)):
    count = db.query(EmailDB).filter(EmailDB.is_unread == True).count()
    return {"count": count}

@app.post("/api/email/mark-all-read")
def mark_all_emails_read(db: Session = Depends(get_db)):
    updated = db.query(EmailDB).filter(EmailDB.is_unread == True).update(
        {EmailDB.is_unread: False}, synchronize_session=False
    )
    db.commit()
    return {"updated": updated}

@app.get("/api/email/{email_id}")
def get_email(email_id: str, db: Session = Depends(get_db)):
    email = db.query(EmailDB).filter(EmailDB.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    result = serialize_email(email)
    result["body"] = email.body
    result["html_body"] = email.html_body or ""
    return result

@app.post("/api/email/{email_id}/summarize")
async def summarize_email(email_id: str, db: Session = Depends(get_db)):
    email = db.query(EmailDB).filter(EmailDB.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    content = (email.body or email.snippet or "").strip()
    if not content:
        raise HTTPException(status_code=422, detail="This email has no readable text to summarize.")

    model = await ollama_client.get_model()
    if not model:
        raise HTTPException(status_code=503, detail="No Ollama model is available. Pull one first (e.g. `ollama pull mistral`).")

    prompt = (
        f"Summarize this email in 2-3 sentences. Be concise and factual.\n\n"
        f"From: {email.sender}\nSubject: {email.subject}\n\n{content[:4000]}"
    )
    try:
        summary = (await ollama_client.generate(model, [{"role": "user", "content": prompt}], temperature=0.3)).strip()
    except Exception:
        raise HTTPException(status_code=502, detail="The model couldn't generate a summary. Check that Ollama is running.")

    if not summary:
        raise HTTPException(status_code=502, detail="The model returned an empty summary. Check that Ollama is running.")

    return {"summary": summary}


# ── Workspace reset ──────────────────────────────────────────────────────────
# The client must echo this string back for the wipe to run, so a stray, replayed,
# or CSRF-style POST to /api/reset can't destroy the workspace on its own.
RESET_CONFIRM_TOKEN = "DELETE EVERYTHING"

# Children before parents: automation artifacts reference runs, attachments and
# tasks; runs reference rules and emails; messages reference conversations.
_RESET_ORDER = [
    ("automation_artifacts", AutomationArtifactDB),
    ("automation_runs", AutomationRunDB),
    ("email_attachments", EmailAttachmentDB),
    ("messages", MessageDB),
    ("emails", EmailDB),
    ("automation_rules", AutomationRuleDB),
    ("tasks", TaskDB),
    ("notes", NoteDB),
    ("calendar_events", CalendarEventDB),
    ("conversations", ConversationDB),
]


def _wipe_sql() -> dict[str, int]:
    """Empty every content table. Sync SQLAlchemy — call via asyncio.to_thread.

    Opens its own session rather than borrowing the request-scoped one, since that
    session belongs to the event loop's thread.
    """
    deleted: dict[str, int] = {}
    with SessionLocal() as db:
        stored_names = [
            row[0] for row in db.query(EmailAttachmentDB.stored_name).all() if row[0]
        ]
        for label, model in _RESET_ORDER:
            deleted[label] = db.query(model).delete(synchronize_session=False)
        db.commit()

    # Attachment blobs live outside the DB, so the rows going away doesn't reclaim them.
    # stored_name is a generated uuid, but bound it to the directory anyway — same
    # guard the download route uses, and this loop unlinks.
    attachments_root = ATTACHMENTS_DIR.resolve()
    for name in stored_names:
        path = (ATTACHMENTS_DIR / name).resolve()
        if path.parent != attachments_root:
            logger.warning("Skipping out-of-tree attachment path during reset: %s", name)
            continue
        with suppress(OSError):
            path.unlink(missing_ok=True)

    return deleted


@app.post("/api/reset")
async def reset_workspace(data: ResetRequest):
    """Delete all workspace content: chats, notes, tasks, events, emails,
    automations, memories and documents.

    Deliberately does **not** touch the saved email credentials — resetting the
    workspace shouldn't silently unlink the user's mailbox. Disconnecting is a
    separate, explicit action (`POST /api/email/disconnect`).
    """
    if data.confirm != RESET_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=400,
            detail=f"Reset not confirmed. Send {{\"confirm\": \"{RESET_CONFIRM_TOKEN}\"}} to proceed.",
        )

    logger.warning("Workspace reset requested — deleting all content.")
    deleted = await asyncio.to_thread(_wipe_sql)

    try:
        deleted["memories"] = await asyncio.to_thread(memory_manager.clear_all)
    except Exception as e:
        logger.error("Failed to clear memories during reset: %s", e)
        deleted["memories"] = -1

    try:
        deleted["documents"] = await asyncio.to_thread(document_manager.clear_all)
    except Exception as e:
        logger.error("Failed to clear documents during reset: %s", e)
        deleted["documents"] = -1

    total = sum(v for v in deleted.values() if v > 0)
    logger.warning("Workspace reset complete: %s items removed.", total)
    return {"status": "reset", "deleted": deleted, "total": total}


frontend_path = BASE_DIR / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
