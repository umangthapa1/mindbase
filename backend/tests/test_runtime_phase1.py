"""Runtime regressions: run via run_isolated.py, never against personal storage."""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import (Base, CapabilityDB, ReminderDB, TaskDB, WorkspaceComponentDB,
                      WorkspaceEventDB, WorkspaceNotificationDB)
from capabilities import seed_capabilities
from workspace_planner import ReminderInputs, reminder_plan
from workspace_runtime import create_reminder, process_due, reminder_action, serialize_component, utcnow
from test_chat_tool_routing import chat_client, send


@pytest.mark.parametrize("message,seconds,label", [
    ("remind me to check on grandpa in 30 seconds", 30, "Check on grandpa"),
    ("can u remind me to stretch in 1 second", 1, "Stretch"),
    ("Please remind me to breathe in 3sec", 3, "Breathe"),
    ("remind me to drink water in 4 secs", 4, "Drink water"),
    ("remind me to look away in 5s", 5, "Look away"),
    ("create a reminder to call Alice in 2 minutes", 120, "Call Alice"),
    ("remind me to sleep in 1 hour and 2 minutes", 3720, "Sleep"),
    ("set a timer for 30 seconds", 30, "Timer"),
    ("start a timer for 1 minute to stretch", 60, "Stretch"),
])
def test_reminder_is_not_a_task_or_model_call(chat_client, message, seconds, label):
    client, db = chat_client
    _, meta, reply = send(client, message)
    assert meta["tool"] == "reminder"
    assert meta["plan"]["inputs"] == {"label": label, "duration_seconds": seconds}
    assert db.query(TaskDB).count() == 0
    reminder = db.query(ReminderDB).one()
    assert reminder.label == label
    assert (reminder.due_at - reminder.created_at).total_seconds() == seconds
    assert db.query(WorkspaceComponentDB).one().visible
    assert "Created reminder" in reply
    assert db.query(WorkspaceEventDB).one().reminder_id == reminder.id


@pytest.mark.parametrize("message", [
    "remind me to check mail tomorrow", "remind me to call Alice at 3pm",
    "remind me to call Alice every hour", "remind me to stretch in -3 seconds",
    "remind me to stretch in 0 minutes", "remind me to stretch in 1.5 hours",
    "remind me to stretch in 999999999 hours", "remind me", "set a timer for thirty seconds",
    "remind me to stretch in 3 seconds then delete my tasks",
])
def test_unsupported_reminders_clarify_without_mutation(chat_client, message):
    client, db = chat_client
    _, meta, reply = send(client, message)
    assert meta["intent"] == "clarification"
    assert meta["actions"] == []
    assert db.query(TaskDB).count() == db.query(ReminderDB).count() == 0
    assert reply


def test_pause_resume_retains_actual_remaining_time_and_updates_props(chat_client):
    client, db = chat_client
    now = utcnow()
    row = create_reminder(db, ReminderInputs(label="Grandpa", duration_seconds=30), now=now)
    reminder_action(db, row.id, "pause", now + timedelta(seconds=11.25))
    assert row.status == "paused"
    assert row.remaining_seconds == pytest.approx(18.75)
    assert row.due_at is None
    reminder_action(db, row.id, "pause", now + timedelta(seconds=50))
    assert row.remaining_seconds == pytest.approx(18.75)
    process_due(db, now + timedelta(seconds=100))
    assert db.query(WorkspaceNotificationDB).count() == 0
    resumed = reminder_action(db, row.id, "resume", now + timedelta(seconds=100))
    expected = now + timedelta(seconds=118.75)
    assert resumed.due_at == expected
    component = db.get(WorkspaceComponentDB, row.component_id)
    assert serialize_component(db, component)["props"]["due_at"] == expected.isoformat(timespec="milliseconds") + "Z"
    assert client.post(f"/api/workspace/reminders/{row.id}/actions", json={"action": "eval"}).status_code == 422


def test_due_notifications_are_durable_non_consuming_and_explicitly_acknowledged(chat_client):
    client, db = chat_client
    now = utcnow()
    row = create_reminder(db, ReminderInputs(label="Grandpa", duration_seconds=1), now=now)
    process_due(db, now + timedelta(seconds=2))
    process_due(db, now + timedelta(seconds=3))
    assert db.query(WorkspaceNotificationDB).count() == 1
    assert db.query(WorkspaceEventDB).filter_by(type="reminder.due").count() == 1
    assert row.status == "due"
    notifications = client.get("/api/workspace/notifications").json()
    assert client.get("/api/workspace/notifications").json() == notifications
    assert len(notifications) == 1
    assert db.query(WorkspaceNotificationDB).one().acknowledged_at is None
    url = f"/api/workspace/notifications/{notifications[0]['id']}/ack"
    first = client.post(url).json()
    assert client.post(url).json() == first
    assert client.get("/api/workspace/notifications").json() == []


def test_completion_and_cancellation_suppress_later_alerts(chat_client):
    client, db = chat_client
    now = utcnow()
    for action in ("complete", "cancel"):
        row = create_reminder(db, ReminderInputs(label=action, duration_seconds=5), now=now)
        reminder_action(db, row.id, action, now + timedelta(seconds=2))
        assert client.post(f"/api/workspace/reminders/{row.id}/actions", json={"action": "resume"}).status_code == 409
    process_due(db, now + timedelta(seconds=30))
    assert db.query(WorkspaceNotificationDB).count() == 0


def test_close_move_and_restore_are_persistent_and_close_does_not_cancel(chat_client):
    client, db = chat_client
    rows = [create_reminder(db, ReminderInputs(label=label, duration_seconds=60)) for label in ("First", "Second", "Third")]
    url = lambda row: f"/api/workspace/components/{row.component_id}"
    assert client.patch(url(rows[2]), json={"move": "earlier"}).status_code == 200
    assert [c["props"]["label"] for c in client.get("/api/workspace/components").json()] == ["First", "Third", "Second"]
    assert client.patch(url(rows[0]), json={"visible": False}).status_code == 200
    assert db.get(ReminderDB, rows[0].id).status == "active"
    assert client.get("/api/workspace/components").json()[0]["visible"] is False
    assert client.patch(url(rows[0]), json={"visible": True}).json()["visible"] is True
    assert client.patch(url(rows[0]), json={"props": {"code": "alert(1)"}}).status_code == 422


def test_registry_disabled_choices_survive_reseeding_and_block_creation(chat_client):
    client, db = chat_client
    assert len(client.get("/api/capabilities").json()) == 7
    assert client.patch("/api/capabilities/timer", json={"enabled": False}).status_code == 200
    seed_capabilities(db)
    assert db.get(CapabilityDB, "timer").enabled is False
    assert client.post("/api/workspace/reminders", json={"label": "Blocked", "duration_seconds": 1}).status_code == 409
    _, meta, reply = send(client, "remind me to stretch in 5 seconds")
    assert meta["actions"] == []
    assert "Enable" in reply
    assert db.query(ReminderDB).count() == 0


def test_restart_recovers_overdue_and_paused_reminders_without_duplicates(tmp_path):
    path = tmp_path / "runtime.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    now = utcnow()
    with sessionmaker(bind=engine)() as db:
        due = create_reminder(db, ReminderInputs(label="Due", duration_seconds=2), now=now)
        paused = create_reminder(db, ReminderInputs(label="Paused", duration_seconds=60), now=now)
        reminder_action(db, paused.id, "pause", now + timedelta(seconds=1))
        paused_id, due_id = paused.id, due.id
    engine.dispose()
    for _ in range(2):
        engine = create_engine(f"sqlite:///{path}")
        with sessionmaker(bind=engine)() as db:
            seed_capabilities(db)
            process_due(db, now + timedelta(seconds=100))
            assert db.get(ReminderDB, due_id).status == "due"
            assert db.get(ReminderDB, paused_id).remaining_seconds == 59
            assert db.query(WorkspaceNotificationDB).count() == 1
        engine.dispose()


def test_completion_uses_latest_reminder_and_is_idempotent(chat_client):
    client, db = chat_client
    conv, _, _ = send(client, "remind me to call Alice in 60 seconds")
    send(client, "remind me to check on grandpa in 30 seconds", conv)
    _, meta, reply = send(client, "yep, I checked on grandpa", conv)
    assert meta["actions"][0]["action"] == "complete_reminder"
    assert "Completed reminder" in reply
    _, _, reply = send(client, "done", conv)
    assert "Already completed reminder" in reply
    assert db.query(ReminderDB).filter_by(label="Call Alice").one().status == "active"


def test_duplicate_titles_and_mismatched_completion_do_not_guess(chat_client):
    client, db = chat_client
    conv, _, _ = send(client, "remind me to check on grandpa in 60 seconds")
    _, meta, _ = send(client, "I checked another thing", conv)
    assert meta["actions"] == []
    send(client, "remind me to check on grandpa in 30 seconds", conv)
    _, meta, _ = send(client, "done", conv)
    assert meta["actions"] == []
    assert all(row.status == "active" for row in db.query(ReminderDB))


def test_timing_clarification_resumes_the_original_reminder_without_guessing(chat_client):
    client, db = chat_client
    conv, meta, _ = send(client, "remind me to check on grandpa tomorrow")
    assert meta["actions"] == []
    _, meta, _ = send(client, "yes", conv)
    assert meta["actions"] == []
    _, meta, _ = send(client, "in 30 seconds", conv)
    assert meta["plan"]["inputs"] == {"label": "Check on grandpa", "duration_seconds": 30}
    assert db.query(ReminderDB).count() == 1
    assert db.query(TaskDB).count() == 0


def test_reminder_reference_never_falls_back_to_an_older_task(chat_client):
    from database import MessageDB
    client, db = chat_client
    conv, _, _ = send(client, "Add task: call Alice")
    send(client, "remind me to check on grandpa in 30 seconds", conv)
    db.add(MessageDB(conversation_id=conv, role="assistant", content="Anything else?"))
    db.commit()
    _, meta, _ = send(client, "done", conv)
    assert meta["actions"] == []
    assert db.query(TaskDB).one().status == "pending"
    assert db.query(ReminderDB).one().status == "active"


def test_reset_deletes_runtime_children_before_parents_and_keeps_registry(chat_client, monkeypatch):
    from main import _wipe_sql
    import main
    from sqlalchemy import text
    client, db = chat_client
    db.execute(text("PRAGMA foreign_keys=ON"))
    now = utcnow()
    create_reminder(db, ReminderInputs(label="Reset", duration_seconds=1), now=now)
    process_due(db, now + timedelta(seconds=2))
    factory = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr(main, "SessionLocal", factory)
    result = _wipe_sql()
    db.expire_all()
    assert result["reminders"] == result["workspace_notifications"] == result["workspace_components"] == 1
    assert db.query(WorkspaceEventDB).count() == 0
    assert db.query(CapabilityDB).count() == 7
