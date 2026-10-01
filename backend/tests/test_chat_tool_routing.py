"""Routing regressions. Run in isolated storage; never use live workspace data."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from database import Base, CalendarEventDB, ConversationDB, EmailDB, TaskDB, get_db
from main import app, _extract_email_search_terms, _is_email_query
from ollama import ollama_client
from intent_routing import route_message, ROUTING_EXAMPLES, TASK_DETAILS_QUESTION


@pytest.mark.parametrize("message", [
    "remind me to check my email tomorrow",
    "add task: reply to Alice's email",
    "I need to check my inbox tomorrow",
    "Please add check emails from Alice to my tasks",
    "schedule checking my inbox tomorrow",
    "note to reply to Alice's message",
])
def test_task_request_is_not_an_inbox_lookup(message):
    assert not _is_email_query(message)


@pytest.mark.parametrize("message", [
    "any new mail?", "did Alice reply?", "has Alice replied?",
    "check if Alice replied", "show me messages from Alice",
])
def test_email_lookup_is_detected(message):
    assert _is_email_query(message)


def test_reply_query_uses_the_named_sender():
    filters = _extract_email_search_terms("Did Alice reply?")
    assert filters["sender"] == "alice"
    assert filters["sender_only"] is True


@pytest.fixture
def chat_client(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(EmailDB(gmail_id="routing-fixture", sender="Alice <alice@example.com>", subject="Invoice reply", body="The invoice is approved."))
    db.commit()

    async def unexpected_model_call(*args, **kwargs):
        raise AssertionError("Explicit routing must not depend on a model")

    monkeypatch.setattr(ollama_client, "get_model", unexpected_model_call)
    monkeypatch.setattr(ollama_client, "generate", unexpected_model_call)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    # No context manager: application lifespan must not run in API unit tests.
    client = TestClient(app)
    try:
        yield client, db
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        db.close()
        engine.dispose()


def send(client, message, conversation_id=None):
    if conversation_id is None:
        conversation_id = client.post("/api/chat/conversations", json={"title": "Routing regression"}).json()["id"]
    response = client.post("/api/chat/messages", json={
        "conversation_id": conversation_id, "message": message,
        "auto_memory": False, "include_memory": False,
    })
    assert response.status_code == 200, response.text
    frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    return conversation_id, frames[0]["meta"], "".join(frame.get("chunk", "") for frame in frames)


@pytest.mark.parametrize("message", [
    "Remind me to check my email tomorrow",
    "Add task: reply to Alice's email",
    "I need to email Alice",
    "Note to check my inbox tomorrow",
    "Schedule checking my inbox tomorrow",
    "Add check emails from Alice to my tasks",
    "Add task: schedule a meeting with Alice",
])
def test_explicit_task_is_saved_without_model_or_mail_lookup(chat_client, message):
    client, db = chat_client
    _, meta, reply = send(client, message)
    assert meta["tool"] == "add_task"
    assert meta["actions"][0]["action"] == "create_task"
    assert db.query(TaskDB).count() == 1
    assert db.query(CalendarEventDB).count() == 0
    assert "Created task" in reply
    assert "Invoice reply" not in reply
    if "tomorrow" in message.lower():
        assert db.query(TaskDB).one().due_date is not None


@pytest.mark.parametrize("message", ["Any new mail?", "Did Alice reply?", "Check messages from Alice"])
def test_mail_lookup_never_creates_tasks(chat_client, message):
    client, db = chat_client
    _, meta, reply = send(client, message)
    assert meta["tool"] == "check_mail"
    assert "Invoice reply" in reply
    assert db.query(TaskDB).count() == 0
    assert db.query(CalendarEventDB).count() == 0


@pytest.mark.parametrize("message", ["Email Alice", "Reply to Alice", "Check Alice", "Add", "Add task", "Add task:"])
def test_ambiguous_request_asks_one_question_without_actions(chat_client, message):
    client, db = chat_client
    _, meta, reply = send(client, message)
    assert meta["intent"] == "clarification"
    assert meta["actions"] == []
    assert reply.count("?") == 1
    assert db.query(TaskDB).count() == 0
    assert db.query(CalendarEventDB).count() == 0


def test_clarification_answer_resumes_the_original_task(chat_client):
    client, db = chat_client
    conv_id, _, _ = send(client, "Email Alice")
    _, meta, _ = send(client, "add a task", conv_id)
    assert meta["tool"] == "add_task"
    assert db.query(TaskDB).one().title == "Email Alice"


def test_clarification_answer_resumes_the_mail_lookup(chat_client):
    client, db = chat_client
    conv_id, _, _ = send(client, "Email Alice")
    _, meta, reply = send(client, "check mail", conv_id)
    assert meta["tool"] == "check_mail"
    assert "Invoice reply" in reply
    assert db.query(TaskDB).count() == 0


def test_explicit_task_overrides_recent_inbox_context(chat_client):
    client, db = chat_client
    conv_id, _, _ = send(client, "Any new mail?")
    _, meta, _ = send(client, "Remind me to reply tomorrow", conv_id)
    assert meta["tool"] == "add_task"
    assert db.query(TaskDB).count() == 1


@pytest.mark.parametrize("message,tool", ROUTING_EXAMPLES)
def test_documented_routing_examples(message, tool):
    assert route_message(message).tool == tool


def test_unclear_answer_reasks_without_losing_original_request(chat_client):
    client, db = chat_client
    conv_id, _, _ = send(client, "Email Alice")
    _, meta, reply = send(client, "yes", conv_id)
    assert meta["intent"] == "clarification"
    assert reply.count("?") == 1
    assert db.query(TaskDB).count() == 0
    send(client, "add a task", conv_id)
    assert db.query(TaskDB).one().title == "Email Alice"


@pytest.mark.parametrize("message", ["do not add anything", "cancel", "no thanks"])
def test_clarification_does_not_override_cancellation(message):
    history = [{"role": "user", "content": "Add"}, {"role": "assistant", "content": TASK_DETAILS_QUESTION}]
    assert route_message(message, history).tool == "chat"


def test_local_tasks_get_titles_without_background_model_calls(chat_client):
    client, db = chat_client
    conv_id = client.post("/api/chat/conversations", json={}).json()["id"]
    send(client, "Add task: Buy milk tomorrow", conv_id)
    assert db.query(ConversationDB).filter_by(id=conv_id).one().title == "Add task: Buy milk tomorrow"


@pytest.mark.parametrize("message", [
    "Write a Python function", "Write a script to check email",
    "What is email?", "How do I check email?", "do not mark Pay rent as done",
])
def test_general_chat_never_reaches_action_extractor(chat_client, monkeypatch, message):
    from types import SimpleNamespace
    from intelligence import chat_intelligence
    from tasks_service import task_manager
    client, db = chat_client

    async def model(requested=None):
        return requested or "selected-model"

    async def unexpected_action(*args, **kwargs):
        raise AssertionError("A general chat request cannot run a scheduling action")

    async def prepared(**kwargs):
        assert kwargs["user_message"] == message
        assert kwargs["model"] == "selected-model"
        return SimpleNamespace(messages=[{"role": "user", "content": message}], intent="general", context_sources=[])

    async def stream(model, messages, **kwargs):
        yield "Ordinary chat answer"

    monkeypatch.setattr(ollama_client, "get_model", model)
    monkeypatch.setattr(ollama_client, "stream_generate", stream)
    monkeypatch.setattr(chat_intelligence, "prepare_chat", prepared)
    monkeypatch.setattr(task_manager, "process_with_history", unexpected_action)
    _, meta, reply = send(client, message)
    assert meta["actions"] == []
    assert reply == "Ordinary chat answer"
    assert db.query(TaskDB).count() == 0


def test_email_summary_keeps_inbox_context_and_selected_model(chat_client, monkeypatch):
    from types import SimpleNamespace
    from intelligence import chat_intelligence
    client, db = chat_client

    async def model(requested=None):
        return "selected-model"

    async def prepared(**kwargs):
        return SimpleNamespace(messages=[{"role": "system", "content": "Test instructions"}], intent="general", context_sources=[])

    async def stream(model, messages, **kwargs):
        assert model == "selected-model"
        assert any("The invoice is approved" in message["content"] for message in messages)
        yield "Alice approved the invoice."

    monkeypatch.setattr(ollama_client, "get_model", model)
    monkeypatch.setattr(ollama_client, "stream_generate", stream)
    monkeypatch.setattr(chat_intelligence, "prepare_chat", prepared)
    _, meta, reply = send(client, "Summarize the email from Alice")
    assert meta["tool"] == "check_mail"
    assert meta["intent"] == "email"
    assert "emails" in meta["context"]
    assert reply == "Alice approved the invoice."
    assert db.query(TaskDB).count() == 0


def test_calendar_actions_still_use_the_existing_handler(chat_client, monkeypatch):
    from datetime import datetime
    from tasks_service import task_manager, ActionResult
    client, db = chat_client

    async def model(requested=None):
        return "selected-model"

    async def action(message, history, session, model=None):
        assert model == "selected-model"
        assert message == "Add an event: team meeting tomorrow at 3pm"
        event = task_manager.create_event(session, "Team meeting", datetime(2026, 10, 2, 15))
        return [ActionResult("create_event", True, "Added team meeting", event.id, "event").to_dict()]

    monkeypatch.setattr(ollama_client, "get_model", model)
    monkeypatch.setattr(task_manager, "process_with_history", action)
    _, meta, reply = send(client, "Add an event: team meeting tomorrow at 3pm")
    assert meta["intent"] == "calendar"
    assert reply == "Added team meeting"
    assert db.query(CalendarEventDB).count() == 1
    assert db.query(TaskDB).count() == 0


@pytest.mark.parametrize("message,tool", [
    ("from Alice", "check_mail"),
    ("summarize the one from Alice", "check_mail"),
    ("summarize this document", "chat"),
    ("delete the task Reply to Alice's email", "schedule"),
    ("mark Reply to Alice as done", "schedule"),
    ("give me a summary of my emails", "check_mail"),
])
def test_followup_context_does_not_override_explicit_targets(message, tool):
    history = [{"role": "user", "content": "Any new mail?"}]
    assert route_message(message, history).tool == tool


def test_task_confirmation_ends_old_inbox_context():
    history = [
        {"role": "user", "content": "Any new mail?"},
        {"role": "user", "content": "Add reply to Alice to my tasks"},
        {"role": "assistant", "content": "Created task: **Reply to Alice**"},
    ]
    assert route_message("or Google?", history).tool != "check_mail"


def test_local_task_retains_due_priority_and_tags(chat_client):
    from datetime import datetime, timedelta
    client, db = chat_client
    send(client, "Add task: Pay rent tomorrow high priority #finance")
    task = db.query(TaskDB).one()
    assert task.title.lower() == "pay rent"
    assert task.priority == "high"
    assert task.status == "pending"
    assert task.due_date.date() == datetime.now().date() + timedelta(days=1)
    assert "finance" in task.tags


def test_local_tools_do_not_extract_unrequested_memories(chat_client, monkeypatch):
    from memory import memory_manager
    client, db = chat_client
    calls = []

    async def extract(*args):
        calls.append(args)

    monkeypatch.setattr(memory_manager, "auto_extract_memory_from_chat", extract)
    conv_id = client.post("/api/chat/conversations", json={"title": "Routing regression"}).json()["id"]
    response = client.post("/api/chat/messages", json={
        "conversation_id": conv_id, "message": "Add task: remember to email Alice",
        "auto_memory": True,
    })
    assert response.status_code == 200
    assert db.query(TaskDB).count() == 1
    assert calls == []


@pytest.mark.parametrize("message,intent", [
    ("Check my tasks", "planning"),
    ("Check my calendar", "calendar"),
    ("Show me tasks about email", "planning"),
])
def test_existing_task_and_calendar_lookups_remain_local(chat_client, message, intent):
    client, db = chat_client
    _, meta, reply = send(client, message)
    assert meta["intent"] == intent
    assert meta["actions"] == []
    assert "Invoice reply" not in reply
    assert db.query(TaskDB).count() == 0
    assert db.query(CalendarEventDB).count() == 0


def test_reported_reminder_conversation_persists_timing_and_completion(chat_client, monkeypatch):
    from datetime import datetime
    import tasks_service
    client, db = chat_client

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 1, 9, 34, 42)

    monkeypatch.setattr(tasks_service, "datetime", FixedDatetime)
    message = "i need to push my projects code to my github can u remind me to do it in like 15 mins"
    conv_id, meta, reply = send(client, message)
    task = db.query(TaskDB).one()
    task_id = task.id
    assert task.title == "Push my projects code to my github"
    assert task.due_date == datetime(2026, 10, 1, 9, 49, 42)
    assert "09:49" in reply
    assert meta["actions"][0]["item_id"] == task_id

    _, meta, reply = send(client, "yep done", conv_id)
    assert meta["actions"][0]["action"] == "complete_task"
    assert meta["actions"][0]["item_id"] == task_id
    assert "Completed task" in reply
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "completed"

    _, meta, reply = send(client, "yep i pushed the code", conv_id)
    assert meta["actions"][0]["item_id"] == task_id
    assert "already completed" in reply.lower()
    assert db.query(TaskDB).count() == 1


@pytest.mark.parametrize("followup", [
    "yep done", "Yep, done!", "yeah I did it", "I'm done",
    "I have finished it", "yep i pushed the code", "I pushed the code",
    "mark it as complete", "I've already pushed it", "done, thanks",
])
def test_recent_task_completion_is_local_and_persisted(chat_client, followup):
    client, db = chat_client
    conv_id, _, _ = send(client, "Add task: push my code to GitHub")
    task_id = db.query(TaskDB).one().id
    _, meta, reply = send(client, followup, conv_id)
    assert meta["actions"][0]["action"] == "complete_task"
    assert meta["actions"][0]["success"] is True
    assert meta["actions"][0]["item_id"] == task_id
    assert "Completed task" in reply
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "completed"
    assert db.query(TaskDB).count() == 1


def test_repeated_completion_does_not_complete_an_older_task(chat_client):
    client, db = chat_client
    conv_id, _, _ = send(client, "Add task: buy milk")
    older = db.query(TaskDB).one()
    send(client, "Add task: push my code to GitHub", conv_id)
    send(client, "yep done", conv_id)
    _, _, reply = send(client, "yep i pushed the code", conv_id)
    db.refresh(older)
    assert older.status == "pending"
    assert "already completed" in reply.lower()
    assert db.query(TaskDB).filter_by(status="completed").count() == 1


@pytest.mark.parametrize("setup", ["none", "multiple", "duplicate", "deleted"])
def test_unclear_completion_does_not_guess_a_task(chat_client, setup):
    client, db = chat_client
    conv_id = None
    if setup != "none":
        conv_id, _, _ = send(client, "Add task: push code")
        if setup == "multiple":
            send(client, "Add task: buy milk", conv_id)
            send(client, "Show my tasks", conv_id)
        elif setup == "duplicate":
            send(client, "Add task: push code", conv_id)
        elif setup == "deleted":
            task = db.query(TaskDB).one()
            client.delete(f"/api/tasks/{task.id}")
    _, meta, reply = send(client, "yep done", conv_id)
    assert meta["intent"] == "clarification"
    assert reply.count("?") == 1
    assert db.query(TaskDB).filter_by(status="completed").count() == 0


@pytest.mark.parametrize("message", ["yep I emailed Alice", "I pushed different code"])
def test_different_activity_does_not_complete_the_recent_task(chat_client, message):
    client, db = chat_client
    conv_id, _, _ = send(client, "Add task: push my code to GitHub")
    _, meta, reply = send(client, message, conv_id)
    assert meta["intent"] == "clarification"
    assert reply.count("?") == 1
    assert db.query(TaskDB).one().status == "pending"


@pytest.mark.parametrize("message", [
    "yep not done", "yep I haven't pushed the code", "yep I will push the code tomorrow",
    "am I done?", "I'm not done", "I haven't finished it",
    "it is not done", "it isn't done", "it will be done tomorrow",
])
def test_negated_future_or_question_followups_are_not_completion_actions(message):
    history = [{"role": "assistant", "content": "Created task: **Push my code to GitHub**"}]
    assert route_message(message, history).tool not in {"complete_task", "schedule", "add_task"}


@pytest.mark.parametrize("delay", ["-15 mins", "0 minutes"])
def test_invalid_reminder_delay_requests_clarification_without_saving(chat_client, delay):
    client, db = chat_client
    _, meta, reply = send(client, f"Remind me to push code in {delay}")
    assert meta["intent"] == "clarification"
    assert reply.count("?") == 1
    assert db.query(TaskDB).count() == 0


def test_informal_can_u_reminder_stays_on_the_local_task_path(chat_client):
    from datetime import datetime, timedelta
    client, db = chat_client
    before = datetime.now()
    _, meta, reply = send(client, "can u remind me to push code in like 15 mins")
    after = datetime.now()
    task = db.query(TaskDB).one()
    assert task.title == "Push code"
    assert before + timedelta(minutes=15) <= task.due_date <= after + timedelta(minutes=15)
    assert meta["tool"] == "add_task"
    assert "local time" in reply
