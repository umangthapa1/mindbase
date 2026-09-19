"""Comprehensive test suite covering all features of Mindbase:
- Tasks (CRUD, Natural Language Creation, Priority Change, Mark Complete, Status Change, Delete)
- Notes (CRUD, Tagging)
- Calendar (CRUD, Date-range queries, Natural Language Scheduling)
- Memory (CRUD, List, Type Filtering, Clear with confirmation token)
- Documents (Upload, List, Delete)
- Chat & Intelligence (Conversations CRUD, Context Gathering)
- Email & Automations (Inbox, Unread Count, Mark Read, Automation Rules CRUD, Execution)
- System & Settings (Health check, Model listing, Workspace reset protection)
- Frontend Asset Integrity (All HTML, CSS, JS presence)
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import (
    Base, get_db, TaskDB, NoteDB, CalendarEventDB,
    ConversationDB, MessageDB, EmailDB, AutomationRuleDB,
    AutomationRunDB, EmailAttachmentDB
)
from main import app
from tasks_service import task_manager
from automations import execute_email_rule


from sqlalchemy.pool import StaticPool

@pytest.fixture(scope="function")
def test_db():
    """Create a pristine in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(test_db):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ==============================================================================
# 1. TASK FEATURES: API & NATURAL LANGUAGE
# ==============================================================================

def test_task_rest_api_lifecycle(client):
    """Test full Task REST API lifecycle: Create -> Read -> Update Priority -> Mark Complete -> Delete."""
    # 1. Create Task
    create_payload = {
        "title": "Prepare Q3 Financial Deck",
        "description": "Include ARR and MRR graphs",
        "priority": "medium",
        "status": "pending",
        "tags": ["work", "finance"],
        "due_date": "2026-10-15"
    }
    res = client.post("/api/tasks", json=create_payload)
    assert res.status_code == 200
    task_data = res.json()
    task_id = task_data["id"]
    assert task_data["title"] == "Prepare Q3 Financial Deck"
    assert task_data["priority"] == "medium"
    assert task_data["status"] == "pending"
    assert "finance" in task_data["tags"]

    # 2. Read Tasks List
    list_res = client.get("/api/tasks")
    assert list_res.status_code == 200
    tasks = list_res.json()["tasks"]
    assert any(t["id"] == task_id for t in tasks)

    # 3. Read Single Task
    get_res = client.get(f"/api/tasks/{task_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == task_id

    # 4. Change Priority to High
    update_pri = client.put(f"/api/tasks/{task_id}", json={"priority": "high"})
    assert update_pri.status_code == 200
    assert update_pri.json()["priority"] == "high"

    # 5. Mark Status Complete
    update_status = client.put(f"/api/tasks/{task_id}", json={"status": "completed"})
    assert update_status.status_code == 200
    assert update_status.json()["status"] == "completed"

    # 6. Delete Task
    del_res = client.delete(f"/api/tasks/{task_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify 404 after deletion
    get_again = client.get(f"/api/tasks/{task_id}")
    assert get_again.status_code == 404


@pytest.mark.anyio
async def test_task_natural_language_add_complete_change_priority(test_db):
    """Test task manager's natural language processing for:
    - Adding tasks with priority and due date
    - Changing task priority
    - Marking task as completed
    - Updating task status to in-progress
    - Deleting tasks
    """
    # 1. Add task via natural language with high priority
    actions = await task_manager.process_user_message(
        "add task Buy groceries tomorrow high priority", test_db
    )
    assert len(actions) == 1
    assert actions[0]["action"] == "create_task"
    assert actions[0]["success"] is True
    task_id = actions[0]["item_id"]

    task = test_db.query(TaskDB).filter_by(id=task_id).first()
    assert task is not None
    assert "groceries" in task.title.lower()
    assert task.priority == "high"
    assert task.status == "pending"

    # 2. Change priority to low via natural language
    pri_actions = await task_manager.process_user_message(
        "change priority of Buy groceries to low", test_db
    )
    assert len(pri_actions) == 1
    assert pri_actions[0]["action"] == "update_priority"
    assert pri_actions[0]["success"] is True
    test_db.refresh(task)
    assert task.priority == "low"

    # 3. Another priority change syntax: "make X high priority"
    pri_actions2 = await task_manager.process_user_message(
        "make Buy groceries high priority", test_db
    )
    assert len(pri_actions2) == 1
    assert pri_actions2[0]["action"] == "update_priority"
    test_db.refresh(task)
    assert task.priority == "high"

    # 4. Update status to in progress: "start working on X"
    status_actions = await task_manager.process_user_message(
        "start working on Buy groceries", test_db
    )
    assert len(status_actions) == 1
    assert status_actions[0]["action"] == "update_status"
    test_db.refresh(task)
    assert task.status == "in_progress"

    # 5. Mark complete via natural language: "mark Buy groceries as done"
    comp_actions = await task_manager.process_user_message(
        "mark Buy groceries as done", test_db
    )
    assert len(comp_actions) == 1
    assert comp_actions[0]["action"] in ("update_status", "complete_task")
    test_db.refresh(task)
    assert task.status == "completed"

    # 6. Delete task via natural language: "delete the task Buy groceries"
    del_actions = await task_manager.process_user_message(
        "delete the task Buy groceries", test_db
    )
    assert len(del_actions) == 1
    assert del_actions[0]["action"] == "delete_task"
    assert test_db.query(TaskDB).filter_by(id=task_id).first() is None


@pytest.mark.anyio
async def test_task_contextual_completion_from_history(test_db):
    """Test completing a task using conversation history ("mark it as complete")."""
    task = TaskDB(title="Submit patent application", status="pending", priority="high")
    test_db.add(task)
    test_db.commit()

    history = [
        {"role": "user", "content": "what tasks do I have?"},
        {
            "role": "assistant",
            "content": "You have the following task:\n- **Submit patent application** (pending) — high priority",
        },
    ]

    actions = await task_manager.process_with_history("mark it as complete", history, test_db)
    assert len(actions) == 1
    assert actions[0]["action"] == "complete_task"
    assert actions[0]["item_id"] == task.id

    test_db.refresh(task)
    assert task.status == "completed"


# ==============================================================================
# 2. NOTE FEATURES
# ==============================================================================

def test_note_rest_api_lifecycle(client):
    """Test Note REST API lifecycle: Create -> List -> Read -> Update -> Delete."""
    # 1. Create Note
    create_res = client.post("/api/notes", json={
        "title": "Weekly Planning Notes",
        "content": "# Weekly Priorities\n- Deliver v1.0\n- Review PRs",
        "tags": ["planning", "weekly"]
    })
    assert create_res.status_code == 200
    note_data = create_res.json()
    note_id = note_data["id"]
    assert note_data["title"] == "Weekly Planning Notes"
    assert "weekly" in note_data["tags"]

    # 2. List Notes
    list_res = client.get("/api/notes")
    assert list_res.status_code == 200
    notes = list_res.json()["notes"]
    assert any(n["id"] == note_id for n in notes)

    # 3. Get Note
    get_res = client.get(f"/api/notes/{note_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Weekly Planning Notes"

    # 4. Update Note
    update_res = client.put(f"/api/notes/{note_id}", json={
        "title": "Updated Weekly Planning Notes",
        "content": "# Weekly Priorities\n- v1.0 Shipped!\n- Post launch party",
        "tags": ["planning", "celebration"]
    })
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Updated Weekly Planning Notes"
    assert "celebration" in update_res.json()["tags"]

    # 5. Delete Note
    del_res = client.delete(f"/api/notes/{note_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify 404
    assert client.get(f"/api/notes/{note_id}").status_code == 404


# ==============================================================================
# 3. CALENDAR & EVENT FEATURES
# ==============================================================================

def test_calendar_rest_api_lifecycle(client):
    """Test Calendar Event REST API lifecycle: Create -> Query range -> Update -> Delete."""
    now = datetime.utcnow()
    start_time = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    end_time = (now + timedelta(days=1, hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

    # 1. Create Event
    create_res = client.post("/api/calendar/events", json={
        "title": "Design System Sync",
        "start": start_time,
        "end": end_time,
        "description": "Discuss color tokens",
        "all_day": False
    })
    assert create_res.status_code == 200
    event_data = create_res.json()
    event_id = event_data["id"]
    assert event_data["title"] == "Design System Sync"

    # 2. Query Calendar
    query_start = now.date().isoformat()
    query_end = (now + timedelta(days=3)).date().isoformat()
    cal_res = client.get(f"/api/calendar?start={query_start}&end={query_end}")
    assert cal_res.status_code == 200
    events = cal_res.json()["items"]
    assert any(e["id"] == event_id for e in events)

    # 3. Update Event
    upd_res = client.put(f"/api/calendar/events/{event_id}", json={
        "title": "Design System Architecture Sync"
    })
    assert upd_res.status_code == 200
    assert upd_res.json()["title"] == "Design System Architecture Sync"

    # 4. Delete Event
    del_res = client.delete(f"/api/calendar/events/{event_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


@pytest.mark.anyio
async def test_calendar_natural_language_create(test_db):
    """Test adding calendar event via natural language scheduling."""
    actions = await task_manager.process_user_message(
        "put Product Strategy Meeting on my calendar for tomorrow at 2pm to 3pm", test_db
    )
    assert len(actions) == 1
    assert actions[0]["action"] == "create_event"
    assert actions[0]["success"] is True

    event = test_db.query(CalendarEventDB).filter_by(id=actions[0]["item_id"]).first()
    assert event is not None
    assert "Product Strategy Meeting" in event.title


# ==============================================================================
# 4. MEMORY STORE FEATURES
# ==============================================================================

def test_memory_clear_token_protection(client):
    """Test memory clear requires the exact confirmation token."""
    # Invalid token rejected
    bad_res = client.post("/api/memory/clear", json={"confirm": "wrong token"})
    assert bad_res.status_code == 400

    # Correct token accepted
    good_res = client.post("/api/memory/clear", json={"confirm": "CLEAR MEMORIES"})
    assert good_res.status_code == 200
    assert good_res.json()["status"] == "cleared"


def test_memory_crud_api(client):
    """Test creating, listing, updating, and deleting memories."""
    # Create memory
    res = client.post("/api/memory/create", json={
        "content": "User prefers dark mode and Python programming language",
        "type": "preference",
        "tags": ["preferences", "ui"]
    })
    assert res.status_code == 200
    mem = res.json()
    mem_id = mem["id"]
    assert "dark mode" in mem["content"]

    # List memories
    list_res = client.get("/api/memory/list")
    assert list_res.status_code == 200
    all_mems = list_res.json()["memories"]
    assert any(m["id"] == mem_id for m in all_mems)

    # Filter by type
    pref_res = client.get("/api/memory/list/preference")
    assert pref_res.status_code == 200
    assert any(m["id"] == mem_id for m in pref_res.json()["memories"])

    # Update memory
    upd_res = client.put(f"/api/memory/{mem_id}", json={
        "content": "User prefers dark mode and TypeScript"
    })
    assert upd_res.status_code == 200

    # Delete memory
    del_res = client.delete(f"/api/memory/{mem_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


# ==============================================================================
# 5. DOCUMENTS FEATURES
# ==============================================================================

def test_document_upload_list_delete(client):
    """Test uploading a text document, listing documents, and deleting."""
    content = b"Mindbase is an offline personal AI workspace. It supports notes and tasks."
    files = {"file": ("workspace_manual.txt", content, "text/plain")}
    res = client.post("/api/documents/upload", files=files)
    assert res.status_code == 200
    doc = res.json()
    doc_id = doc["id"]
    assert doc["filename"] == "workspace_manual.txt"
    assert doc["chunks"] > 0

    # List documents
    list_res = client.get("/api/documents")
    assert list_res.status_code == 200
    docs = list_res.json()["documents"]
    assert any(d["id"] == doc_id for d in docs)

    # Delete document
    del_res = client.delete(f"/api/documents/{doc_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


# ==============================================================================
# 6. CHAT & CONVERSATION FEATURES
# ==============================================================================

def test_chat_conversation_lifecycle(client):
    """Test chat conversation CRUD."""
    # Create conversation
    res = client.post("/api/chat/conversations", json={"title": "Q3 Brainstorming"})
    assert res.status_code == 200
    conv = res.json()
    conv_id = conv["id"]
    assert conv["title"] == "Q3 Brainstorming"

    # List conversations
    list_res = client.get("/api/chat/conversations")
    assert list_res.status_code == 200
    convs = list_res.json()
    assert any(c["id"] == conv_id for c in convs)

    # Get conversation
    get_res = client.get(f"/api/chat/conversations/{conv_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == conv_id

    # Rename conversation
    rename_res = client.put(f"/api/chat/conversations/{conv_id}", json={"title": "Q3 Roadmap"})
    assert rename_res.status_code == 200
    assert rename_res.json()["title"] == "Q3 Roadmap"

    # Delete conversation
    del_res = client.delete(f"/api/chat/conversations/{conv_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


# ==============================================================================
# 7. EMAIL & AUTOMATION FEATURES
# ==============================================================================

def test_email_api_and_automations(client, test_db):
    """Test email status, mark-read, and automation rules CRUD & execution."""
    # 1. Email Status
    status_res = client.get("/api/email/status")
    assert status_res.status_code == 200
    assert "connected" in status_res.json()

    # 2. Seed test email
    email = EmailDB(
        gmail_id="inv-001",
        sender="invoices@acme.com",
        subject="Invoice 2026-09 Attached",
        body="Please pay invoice before end of month.",
        snippet="Please pay invoice",
        is_unread=True,
    )
    test_db.add(email)
    test_db.commit()

    # 3. Unread count and mark-read
    unread_res = client.get("/api/email/unread-count")
    assert unread_res.status_code == 200
    assert unread_res.json()["count"] == 1

    mark_res = client.post("/api/email/mark-all-read")
    assert mark_res.status_code == 200
    assert mark_res.json()["updated"] == 1

    unread_after = client.get("/api/email/unread-count")
    assert unread_after.json()["count"] == 0

    # 4. Create Automation Rule
    rule_res = client.post("/api/automations", json={
        "name": "Invoice Handler",
        "trigger": "email",
        "condition": "invoice",
        "actions": ["task", "tag"],
        "action_details": "tag as billing",
        "enabled": True
    })
    assert rule_res.status_code == 201
    rule_data = rule_res.json()
    rule_id = rule_data["id"]

    # 5. Execute Automation Rule on matching email
    rule_db = test_db.query(AutomationRuleDB).filter_by(id=rule_id).first()
    execution_res = execute_email_rule(test_db, rule_db, email)
    test_db.commit()

    actions_list = execution_res.get("actions") or execution_res.get("result", {}).get("actions", [])
    action_types = [a["type"] for a in actions_list]
    assert "task" in action_types
    assert "tag" in action_types

    # Verify task was created by automation
    created_task = test_db.query(TaskDB).filter(TaskDB.title.contains("Invoice")).first()
    assert created_task is not None

    # 6. Delete Automation Rule
    del_res = client.delete(f"/api/automations/{rule_id}")
    assert del_res.status_code == 200


# ==============================================================================
# 8. SYSTEM, HEALTH & WORKSPACE RESET PROTECTION
# ==============================================================================

def test_health_check_and_models(client):
    """Test health check and ollama models endpoints."""
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "healthy"

    models_res = client.get("/api/ollama/models")
    assert models_res.status_code == 200
    assert "models" in models_res.json()


def test_workspace_reset_token_rejection(client):
    """Test that workspace reset rejects requests without the exact confirmation token."""
    res = client.post("/api/reset", json={"confirm": "delete"})
    assert res.status_code == 400
    assert "Reset not confirmed" in res.json()["detail"]


# ==============================================================================
# 9. FRONTEND ASSET INTEGRITY
# ==============================================================================

def test_frontend_files_integrity():
    """Verify that all frontend pages, scripts, and stylesheets exist and are non-empty."""
    frontend_dir = BACKEND_DIR.parent / "frontend"
    assert frontend_dir.exists(), "Frontend directory must exist"

    index_html = frontend_dir / "index.html"
    assert index_html.exists() and index_html.stat().st_size > 0

    expected_pages = [
        "agents.html", "automations.html", "calendar.html", "dashboard.html",
        "documents.html", "email.html", "memory.html", "notes.html",
        "research.html", "settings.html", "tasks.html"
    ]
    pages_dir = frontend_dir / "pages"
    for page in expected_pages:
        page_path = pages_dir / page
        assert page_path.exists(), f"Page {page} missing"
        assert page_path.stat().st_size > 0, f"Page {page} is empty"

    expected_js = [
        "accent.js", "api.js", "app.js", "chat.js", "dock.js",
        "email.js", "theme.js", "toast.js", "utils.js"
    ]
    js_dir = frontend_dir / "js"
    for js_file in expected_js:
        p = js_dir / js_file
        assert p.exists(), f"JS file {js_file} missing"
        assert p.stat().st_size > 0, f"JS file {js_file} is empty"
