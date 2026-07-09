from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime
from pathlib import Path
import json

from config import API_HOST, API_PORT, DEFAULT_MODEL, BASE_DIR
from imap_service import email_service, serialize_email
from database import init_db, get_db, ConversationDB, MessageDB, SessionLocal, NoteDB, TaskDB, CalendarEventDB, EmailDB
from tasks_service import task_manager, serialize_task, serialize_event, _parse_date_string
from models import (
    Conversation, ConversationCreate, ChatRequest, ChatResponse, Message
)
from ollama import ollama_client
from memory import memory_manager
from documents import document_manager
from research import research_agent
from intelligence import chat_intelligence

app = FastAPI(title="Mindbase AI Workspace")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# ── Email context helpers ────────────────────────────────────────────────────
import re as _re

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
    """Query EmailDB and return a formatted context block for the LLM."""
    if not email_service.is_connected():
        return ""

    filters = _extract_email_search_terms(message)
    q = db.query(EmailDB)

    if filters["unread_only"]:
        q = q.filter(EmailDB.is_unread == True)
    if filters["sender"]:
        # Match the term against the sender OR the subject (covers "from leetcode"
        # as well as "the puzzle one").
        like = f"%{filters['sender']}%"
        q = q.filter(EmailDB.sender.ilike(like) | EmailDB.subject.ilike(like))
    if filters["subject_keywords"]:
        for kw in filters["subject_keywords"][:2]:
            q = q.filter(
                EmailDB.subject.ilike(f"%{kw}%") | EmailDB.snippet.ilike(f"%{kw}%")
            )

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

@app.on_event("startup")
async def startup():
    health = await ollama_client.check_health()
    if health:
        try:
            await ollama_client.get_model()
        except Exception as e:
            print(f"✗ Could not select Ollama model: {e}")
        print(f"✓ Connected to Ollama at {ollama_client.host}")
    else:
        print(f"✗ Could not connect to Ollama at {ollama_client.host}")

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
async def switch_model(data: dict):
    model_name = data.get("model")
    success = await ollama_client.set_model(model_name)
    if success:
        return {"status": "success", "model": model_name}
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

    try:
        model = await ollama_client.get_model(request.model)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    history = []
    for msg in conv.messages:
        if msg.id != user_msg.id:
            history.append({"role": msg.role, "content": msg.content})
    history.append({"role": "user", "content": request.message})

    # Check email intent first — if this is an email query, skip task_manager
    # so it doesn't create a task called "Email Check" instead of fetching emails.
    email_context_block = ""
    if _is_email_query(request.message, history):
        email_context_block = _build_email_context(db, request.message)
        actions_taken = []
        if email_context_block:
            actions_taken.append({"type": "email_context", "summary": "Retrieved emails from Gmail"})
    else:
        actions_taken = await task_manager.process_with_history(
            request.message, history, db, model=model
        )

    prepared = await chat_intelligence.prepare_chat(
        user_message=request.message,
        history=history,
        db=db,
        model=model,
        agent_prompt=request.agent_prompt,
        temperature=request.temperature,
        actions_taken=actions_taken,
        conv=conv,
    )
    messages = prepared.messages
    gen_temperature = request.temperature

    # For email queries, prepend the Gmail context as a high-priority system message
    # so the LLM reads it instead of relying on the schedule/task context injected by
    # chat_intelligence. Insert right after the first system message (index 0) if one
    # exists, otherwise prepend to the front.
    if email_context_block:
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
        print(f"[EMAIL DEBUG] Injected email system message into messages list at position {sys_idx + 1 if sys_idx is not None else 0}")

    async def generate():
        response_text = ""
        meta = {
            "intent": prepared.intent,
            "context": prepared.context_sources,
            "actions": actions_taken,
        }
        yield f"data: {json.dumps({'meta': meta})}\n\n"

        async for chunk in ollama_client.stream_generate(
            model, messages, temperature=gen_temperature
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

        # Auto-extract memory from conversation
        try:
            recent_messages = [
                {"role": m.role, "content": m.content}
                for m in sorted(conv.messages, key=lambda x: x.created_at)[-6:]
            ]
            await memory_manager.auto_extract_memory_from_chat(request.conversation_id, recent_messages)
        except Exception as e:
            print(f"Memory extraction error: {e}")

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
def update_conversation(conversation_id: str, data: dict, db: Session = Depends(get_db)):
    conv = db.query(ConversationDB).filter(ConversationDB.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if "title" in data:
        conv.title = data["title"]

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
async def create_memory(data: dict):
    content = data.get("content")
    memory_type = data.get("type", "reference")
    tags = data.get("tags", [])

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    memory = await memory_manager.create_memory(content, memory_type, tags)
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
async def search_memories(data: dict):
    query = data.get("query")
    memory_type = data.get("type")

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    memories = await memory_manager.search_memories(query, memory_type, limit=10)
    return {"memories": memories, "count": len(memories), "query": query}

@app.put("/api/memory/{memory_id}")
async def update_memory(memory_id: str, data: dict):
    content = data.get("content")
    tags = data.get("tags")
    metadata = data.get("metadata")

    updated = await memory_manager.update_memory(memory_id, content, tags, metadata)
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
        print(f"Error syncing note to memory: {e}")

@app.post("/api/notes")
async def create_note(data: dict, db: Session = Depends(get_db)):
    title = data.get("title", "Untitled")
    content = data.get("content", "")
    tags = data.get("tags", [])

    note = NoteDB(title=title, content=content, tags=",".join(tags))
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
async def update_note(note_id: str, data: dict, db: Session = Depends(get_db)):
    note = db.query(NoteDB).filter(NoteDB.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if "title" in data:
        note.title = data["title"]
    if "content" in data:
        note.content = data["content"]
    if "tags" in data:
        note.tags = ",".join(data["tags"]) if isinstance(data["tags"], list) else data["tags"]

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
def create_task(data: dict, db: Session = Depends(get_db)):
    title = data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    due_raw = data.get("due_date")
    due = _parse_date_string(due_raw) if due_raw else None

    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    task = task_manager.create_task(
        db,
        title,
        description=data.get("description", ""),
        status=data.get("status", "pending"),
        priority=data.get("priority", "medium"),
        due_date=due,
        tags=tags,
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
def update_task(task_id: str, data: dict, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if "title" in data:
        task.title = data["title"]
    if "description" in data:
        task.description = data["description"]
    if "status" in data:
        task.status = data["status"]
    if "priority" in data:
        task.priority = data["priority"]
    if "tags" in data:
        task.tags = ",".join(data["tags"]) if isinstance(data["tags"], list) else data["tags"]
    if "due_date" in data:
        task.due_date = _parse_date_string(data["due_date"]) if data["due_date"] else None

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
def create_calendar_event(data: dict, db: Session = Depends(get_db)):
    title = data.get("title")
    start = _parse_date_string(data.get("start") or data.get("start_at", ""))
    if not title or not start:
        raise HTTPException(status_code=400, detail="title and start are required")

    end = _parse_date_string(data.get("end") or data.get("end_at", ""))
    event = task_manager.create_event(
        db,
        title,
        start,
        end,
        description=data.get("description", ""),
        all_day=bool(data.get("all_day")),
        location=data.get("location", ""),
        color=data.get("color", "violet"),
    )
    return serialize_event(event)


@app.put("/api/calendar/events/{event_id}")
def update_calendar_event(event_id: str, data: dict, db: Session = Depends(get_db)):
    event = db.query(CalendarEventDB).filter(CalendarEventDB.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if "title" in data:
        event.title = data["title"]
    if "description" in data:
        event.description = data["description"]
    if "start" in data or "start_at" in data:
        parsed = _parse_date_string(data.get("start") or data.get("start_at"))
        if parsed:
            event.start_at = parsed
    if "end" in data or "end_at" in data:
        parsed = _parse_date_string(data.get("end") or data.get("end_at"))
        if parsed:
            event.end_at = parsed
    if "all_day" in data:
        event.all_day = 1 if data["all_day"] else 0
    if "location" in data:
        event.location = data["location"]
    if "color" in data:
        event.color = data["color"]

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
async def start_research(data: dict, db: Session = Depends(get_db)):
    query = data.get("query")
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
async def save_research_report(data: dict, db: Session = Depends(get_db)):
    report = data.get("report")
    if not report:
        raise HTTPException(status_code=400, detail="Report is required")

    existing_note_id = report.get("note_id")
    if existing_note_id:
        return {"status": "already_saved", "note_id": existing_note_id}

    note_id = await research_agent.save_report_to_note(report, db)
    return {"status": "saved", "note_id": note_id}
from fastapi import UploadFile, File

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
async def ask_document(document_id: str, data: dict):
    query = data.get("query")
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


# ── Email endpoints (Gmail) ──────────────────────────────────────────────────
@app.get("/api/email/status")
def email_status():
    return {"connected": email_service.is_connected(), "email": email_service.account_email()}

@app.post("/api/email/connect")
def email_connect(data: dict):
    address = (data.get("email") or "").strip()
    password = (data.get("app_password") or "").strip()
    host = (data.get("host") or "").strip()
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
    return {"connected": True, "email": email_service.account_email()}

@app.post("/api/email/disconnect")
def email_disconnect():
    email_service.disconnect()
    return {"status": "disconnected"}

@app.post("/api/email/sync")
def sync_email(data: dict = {}, db: Session = Depends(get_db)):
    if not email_service.is_connected():
        raise HTTPException(status_code=401, detail="Email not connected")
    max_results = data.get("max_results", 20)
    unread_only = bool(data.get("unread_only", False))
    try:
        new_emails = email_service.sync_inbox(db, max_results=max_results, unread_only=unread_only)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach your mail server: {e}")
    return {"new_count": len(new_emails), "emails": [serialize_email(e) for e in new_emails]}

@app.get("/api/email/inbox")
def list_inbox(unread_only: bool = False, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(EmailDB)
    if unread_only:
        q = q.filter(EmailDB.is_unread == True)
    emails = q.order_by(EmailDB.received_at.desc()).limit(limit).all()
    return {"emails": [serialize_email(e) for e in emails], "count": len(emails)}

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
    summary = (await ollama_client.generate(model, [{"role": "user", "content": prompt}], temperature=0.3)).strip()

    # ollama_client.generate returns "[Error: ...]" strings rather than raising.
    if summary.startswith("[Error") or not summary:
        raise HTTPException(status_code=502, detail="The model couldn't generate a summary. Check that Ollama is running.")

    return {"summary": summary}


frontend_path = BASE_DIR / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)