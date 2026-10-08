"""Durable workflow regressions. Use run_isolated.py to protect personal storage."""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import (Base, TaskDB, CalendarEventDB, ReminderDB, WorkflowDB, WorkflowStepDB,
                      WorkflowLinkDB, WorkflowNotificationDB, WorkspaceComponentDB, WorkspaceNotificationDB)
from workflow_planner import WorkflowPlan
from workflow_runtime import create_workflow, process_workflows, serialize_workflow
from workspace_runtime import utcnow, process_due
from tasks_service import task_manager
from test_chat_tool_routing import chat_client, send


def linked_plan(seconds=30):
    return {"title": "Call grandpa", "steps": [
        {"id": "task", "action": "create_task", "inputs": {"title": "Call grandpa"}},
        {"id": "reminder", "action": "create_reminder", "depends_on": ["task"],
         "inputs": {"label": "Call grandpa", "duration_seconds": seconds, "task_step_id": "task"}},
        {"id": "done", "action": "wait_for_reminder", "depends_on": ["reminder"],
         "inputs": {"reminder_step_id": "reminder", "until": "completed"}},
    ]}


def notification_plan():
    return {"title": "Create and confirm", "steps": [
        {"id": "task", "action": "create_task", "inputs": {"title": "Buy milk"}},
        {"id": "confirm", "action": "notify", "depends_on": ["task"], "inputs": {"message": "Task created"}},
    ]}


def submit(client, plan, key=None):
    request = {"plan": plan}
    if key:
        request["idempotency_key"] = key
    return client.post("/api/workspace/workflows", json=request)


@pytest.mark.parametrize("message", [
    "Create a task to call grandpa tomorrow and remind me in 30 minutes",
    "Please add task: call grandpa tomorrow, and can u remind me to do it in 30 mins",
    "workflow: add task: call grandpa tomorrow and remind me to call grandpa in 30 minutes",
])
def test_chat_plans_linked_workflow_locally_without_losing_task_date(chat_client, message):
    client, db = chat_client
    conv, meta, reply = send(client, message)
    assert meta["tool"] == "workflow"
    assert meta["plan"]["capability_id"] == "workflows"
    assert meta["actions"][0]["item_type"] == "workflow"
    assert "Created workflow" in reply
    task, reminder, workflow = db.query(TaskDB).one(), db.query(ReminderDB).one(), db.query(WorkflowDB).one()
    assert task.title == reminder.label == "Call grandpa"
    assert task.due_date is not None
    assert workflow.conversation_id == conv
    assert workflow.status == "running"
    assert db.query(WorkflowLinkDB).one().task_id == task.id
    assert [step.status for step in db.query(WorkflowStepDB).order_by(WorkflowStepDB.position)] == ["completed", "completed", "waiting"]


@pytest.mark.parametrize("message", [
    "Create a task to call Alice and remind me tomorrow",
    "Create a task to call Alice then email Bob",
    "remind me to stretch in 3 seconds then delete my tasks",
    "workflow: create task: Buy milk and notify me",
    "workflow: run Python code then create task: Buy milk",
    "workflow: create task: Buy milk and remind me in -3 seconds",
])
def test_unclear_or_unsupported_workflows_never_execute_a_subset(chat_client, message):
    client, db = chat_client
    _, meta, reply = send(client, message)
    assert meta["intent"] == "clarification"
    assert meta["actions"] == []
    assert reply.count("?") == 1
    assert db.query(WorkflowDB).count() == db.query(TaskDB).count() == db.query(ReminderDB).count() == 0


@pytest.mark.parametrize("message,label", [
    ("Create a task to call grandpa tomorrow and remind me tomorrow", "Call grandpa"),
    ("Create a task to call grandpa tomorrow and remind me to do it tomorrow", "Call grandpa"),
    ("Create a task to call grandpa tomorrow and remind me to stretch tomorrow", "Stretch"),
])
def test_workflow_timing_clarification_resumes_the_complete_plan(chat_client, message, label):
    client, db = chat_client
    conv, meta, _ = send(client, message)
    assert meta["actions"] == []
    _, meta, _ = send(client, "yes", conv)
    assert meta["actions"] == []
    _, meta, _ = send(client, "in 30 seconds", conv)
    assert meta["tool"] == "workflow"
    assert db.query(TaskDB).one().title == "Call grandpa"
    assert db.query(ReminderDB).one().label == label


@pytest.mark.parametrize("change", ["unknown_action", "forward", "cycle", "wrong_reference", "duplicate", "empty_title", "extra_code", "invalid_delay"])
def test_invalid_graphs_and_inputs_are_rejected_before_any_mutation(chat_client, change):
    client, db = chat_client
    plan = linked_plan()
    if change == "unknown_action":
        plan["steps"][0]["action"] = "execute_python"
    elif change in {"forward", "cycle"}:
        plan["steps"][0]["depends_on"] = ["reminder"]
    elif change == "wrong_reference":
        plan["steps"][2]["inputs"]["reminder_step_id"] = "task"
    elif change == "duplicate":
        plan["steps"][1]["id"] = "task"
    elif change == "empty_title":
        plan["steps"][0]["inputs"]["title"] = "  "
    elif change == "extra_code":
        plan["steps"][0]["inputs"]["code"] = "delete_all()"
    elif change == "invalid_delay":
        plan["steps"][1]["inputs"]["duration_seconds"] = 0
    assert submit(client, plan).status_code == 422
    assert db.query(WorkflowDB).count() == db.query(TaskDB).count() == 0


def test_idempotent_submission_and_repeated_ticks_do_not_duplicate_artifacts(chat_client):
    client, db = chat_client
    first = submit(client, linked_plan(), "same-request").json()
    second = submit(client, linked_plan(), "same-request").json()
    assert first["id"] == second["id"]
    for _ in range(4):
        process_workflows(db)
    assert db.query(WorkflowDB).count() == db.query(TaskDB).count() == db.query(ReminderDB).count() == 1
    changed = linked_plan(60)
    assert submit(client, changed, "same-request").status_code == 409
    assert submit(client, linked_plan(), "new-request").status_code == 200
    assert db.query(TaskDB).count() == 2


def test_notification_waits_for_due_reminder_and_uses_acknowledged_delivery(chat_client):
    client, db = chat_client
    _, _, _ = send(client, "remind me to stretch in 5 seconds then notify me that stretching is due")
    workflow = db.query(WorkflowDB).one()
    assert workflow.status == "running"
    assert db.query(WorkflowNotificationDB).count() == 0
    now = db.query(ReminderDB).one().due_at + timedelta(seconds=1)
    process_due(db, now)
    process_workflows(db, now)
    assert workflow.status == "completed"
    notifications = client.get("/api/workspace/notifications").json()
    workflow_notification = next(row for row in notifications if row.get("workflow_id") == workflow.id)
    assert workflow_notification["message"] == "stretching is due"
    assert client.get("/api/workspace/notifications").json() == notifications
    assert client.post(f"/api/workspace/notifications/{workflow_notification['id']}/ack").status_code == 200
    process_workflows(db, now)
    assert db.query(WorkflowNotificationDB).count() == 1


def test_transient_failure_rolls_back_effect_and_retry_skips_successful_steps(chat_client, monkeypatch):
    import workflow_runtime
    client, db = chat_client
    execute = workflow_runtime.execute_step
    failures = 0

    def fail_after_reminder_is_inserted(db, workflow, row, step, now):
        nonlocal failures
        result = execute(db, workflow, row, step, now)
        if step.action == "create_reminder" and failures == 0:
            failures += 1
            raise RuntimeError("Transient local write failure")
        return result

    monkeypatch.setattr(workflow_runtime, "execute_step", fail_after_reminder_is_inserted)
    now = utcnow()
    workflow = create_workflow(db, WorkflowPlan(**linked_plan()), now=now)
    assert db.query(TaskDB).count() == 1
    assert db.query(ReminderDB).count() == db.query(WorkflowLinkDB).count() == 0
    assert db.query(WorkspaceComponentDB).count() == 1  # No orphan countdown after rollback
    result = serialize_workflow(db, workflow)
    assert result["steps"][1]["status"] == "failed"
    assert result["steps"][1]["attempts"] == 1
    process_workflows(db, now + timedelta(seconds=2))
    assert db.query(TaskDB).count() == db.query(ReminderDB).count() == db.query(WorkflowLinkDB).count() == 1
    steps = serialize_workflow(db, workflow)["steps"]
    assert steps[0]["attempts"] == 1
    assert steps[1]["attempts"] == 2
    assert steps[2]["status"] == "waiting"


def test_retry_exhaustion_and_manual_retry_preserve_completed_work(chat_client):
    client, db = chat_client
    client.patch("/api/capabilities/notifications", json={"enabled": False})
    now = utcnow()
    workflow = create_workflow(db, WorkflowPlan(**notification_plan()), now=now)
    process_workflows(db, now + timedelta(seconds=1))
    process_workflows(db, now + timedelta(seconds=3))
    assert workflow.status == "failed"
    assert serialize_workflow(db, workflow)["steps"][1]["attempts"] == 3
    assert db.query(TaskDB).count() == 1
    assert db.query(WorkflowNotificationDB).count() == 0
    process_workflows(db, now + timedelta(days=1))
    assert serialize_workflow(db, workflow)["steps"][1]["attempts"] == 3
    client.patch("/api/capabilities/notifications", json={"enabled": True})
    response = client.post(f"/api/workspace/workflows/{workflow.id}/actions", json={"action": "retry"})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["steps"][0]["attempts"] == 1
    assert db.query(TaskDB).count() == db.query(WorkflowNotificationDB).count() == 1


def test_completion_in_either_direction_updates_exact_link_and_suppresses_alert(chat_client):
    client, db = chat_client
    first = submit(client, linked_plan()).json()
    task_id, reminder_id = first["steps"][0]["result"]["item_id"], first["steps"][1]["result"]["item_id"]
    assert client.put(f"/api/tasks/{task_id}", json={"status": "completed"}).status_code == 200
    assert db.get(ReminderDB, reminder_id).status == "completed"
    assert client.get(f"/api/workspace/workflows/{first['id']}").json()["status"] == "completed"
    second = submit(client, linked_plan()).json()
    second_task, second_reminder = second["steps"][0]["result"]["item_id"], second["steps"][1]["result"]["item_id"]
    assert client.post(f"/api/workspace/reminders/{second_reminder}/actions", json={"action": "complete"}).status_code == 200
    assert db.get(TaskDB, second_task).status == "completed"
    process_due(db, utcnow() + timedelta(hours=1))
    assert db.query(WorkspaceNotificationDB).count() == 0
    assert db.get(WorkflowDB, second["id"]).status == "completed"


def test_chat_completion_is_grounded_and_idempotent(chat_client):
    client, db = chat_client
    conv, _, _ = send(client, "Create a task to call grandpa tomorrow and remind me in 30 minutes")
    _, meta, reply = send(client, "I called grandpa", conv)
    assert meta["actions"][0]["action"] == "complete_workflow_task"
    assert "Completed workflow task" in reply
    _, _, reply = send(client, "done", conv)
    assert "Already completed" in reply
    assert db.query(TaskDB).one().status == db.query(ReminderDB).one().status == "completed"


def test_ambiguous_workflow_completion_does_not_select_an_old_task(chat_client):
    client, db = chat_client
    conv, _, _ = send(client, "Add task: call Alice")
    message = "Create a task to call grandpa tomorrow and remind me in 30 minutes"
    send(client, message, conv)
    _, meta, _ = send(client, "I called somebody different", conv)
    assert meta["actions"] == []
    send(client, message, conv)
    _, meta, _ = send(client, "done", conv)
    assert meta["actions"] == []
    assert db.query(TaskDB).filter_by(status="completed").count() == 0


def test_cancel_stops_future_steps_and_owned_alerts_without_deleting_task(chat_client):
    client, db = chat_client
    workflow = submit(client, linked_plan()).json()
    url = f"/api/workspace/workflows/{workflow['id']}/actions"
    assert client.post(url, json={"action": "cancel"}).json()["status"] == "cancelled"
    assert client.post(url, json={"action": "cancel"}).status_code == 200
    assert client.post(url, json={"action": "retry"}).status_code == 409
    assert db.query(TaskDB).one().status == "pending"
    assert db.query(ReminderDB).one().status == "cancelled"
    process_due(db, utcnow() + timedelta(days=1))
    process_workflows(db)
    assert db.query(WorkspaceNotificationDB).count() == 0
    assert client.get(f"/api/workspace/workflows/{workflow['id']}").json()["steps"][-1]["status"] == "cancelled"


def test_cancelled_reminder_cancels_its_waiting_workflow(chat_client):
    client, db = chat_client
    workflow = submit(client, linked_plan()).json()
    reminder_id = workflow["steps"][1]["result"]["item_id"]
    client.post(f"/api/workspace/reminders/{reminder_id}/actions", json={"action": "cancel"})
    assert db.get(WorkflowDB, workflow["id"]).status == "cancelled"


def test_calendar_step_is_transactional_and_dates_are_validated(chat_client):
    client, db = chat_client
    plan = {"title": "Team meeting", "steps": [
        {"id": "meeting", "action": "create_calendar_event", "inputs": {
            "title": "Team meeting", "start_at": "2026-10-07T09:00:00", "end_at": "2026-10-07T10:00:00"}},
        {"id": "notice", "action": "notify", "depends_on": ["meeting"], "inputs": {"message": "Meeting scheduled"}},
    ]}
    assert submit(client, plan, "calendar-request").json()["status"] == "completed"
    assert submit(client, plan, "calendar-request").status_code == 200
    assert db.query(CalendarEventDB).count() == 1
    plan["steps"][0]["inputs"]["end_at"] = "2026-10-07T08:00:00"
    assert submit(client, plan).status_code == 422


def test_disabled_workflow_creation_and_deleted_linked_task_are_handled(chat_client):
    client, db = chat_client
    client.patch("/api/capabilities/workflows", json={"enabled": False})
    assert submit(client, linked_plan()).status_code == 409
    assert db.query(WorkflowDB).count() == 0
    client.patch("/api/capabilities/workflows", json={"enabled": True})
    workflow = submit(client, linked_plan()).json()
    task_id, reminder_id = workflow["steps"][0]["result"]["item_id"], workflow["steps"][1]["result"]["item_id"]
    assert client.delete(f"/api/tasks/{task_id}").status_code == 200
    assert db.query(WorkflowLinkDB).one().task_id is None
    assert client.post(f"/api/workspace/reminders/{reminder_id}/actions", json={"action": "complete"}).status_code == 200
    assert db.query(TaskDB).count() == 0


def test_restart_continues_wait_then_creates_next_task_once(tmp_path):
    path = tmp_path / "workflows.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    now = utcnow()
    plan = WorkflowPlan(title="Delayed follow-up", steps=[
        {"id": "reminder", "action": "create_reminder", "inputs": {"label": "Stretch", "duration_seconds": 5}},
        {"id": "wait", "action": "wait_for_reminder", "depends_on": ["reminder"], "inputs": {"reminder_step_id": "reminder"}},
        {"id": "task", "action": "create_task", "depends_on": ["wait"], "inputs": {"title": "Drink water"}},
    ])
    with sessionmaker(bind=engine)() as db:
        workflow_id = create_workflow(db, plan, now=now).id
        assert db.query(TaskDB).count() == 0
    engine.dispose()
    for _ in range(2):
        engine = create_engine(f"sqlite:///{path}")
        with sessionmaker(bind=engine)() as db:
            process_due(db, now + timedelta(seconds=10))
            process_workflows(db, now + timedelta(seconds=10))
            assert db.get(WorkflowDB, workflow_id).status == "completed"
            assert db.query(TaskDB).count() == db.query(ReminderDB).count() == 1
        engine.dispose()


def test_crash_before_step_commit_rolls_back_effect_and_resumes_after_restart(tmp_path, monkeypatch):
    import workflow_runtime
    path = tmp_path / "crash.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    execute = workflow_runtime.execute_step

    class SimulatedCrash(BaseException):
        pass

    def crash_after_write(*args):
        execute(*args)
        raise SimulatedCrash()

    with sessionmaker(bind=engine)() as db:
        monkeypatch.setattr(workflow_runtime, "execute_step", crash_after_write)
        with pytest.raises(SimulatedCrash):
            create_workflow(db, WorkflowPlan(**notification_plan()))
        db.rollback()
        assert db.query(TaskDB).count() == 0
        assert db.query(WorkflowStepDB).first().status == "pending"
    engine.dispose()
    monkeypatch.setattr(workflow_runtime, "execute_step", execute)
    engine = create_engine(f"sqlite:///{path}")
    with sessionmaker(bind=engine)() as db:
        process_workflows(db)
        assert db.query(WorkflowDB).one().status == "completed"
        assert db.query(TaskDB).count() == db.query(WorkflowNotificationDB).count() == 1
    engine.dispose()


def test_reset_removes_workflow_graph_and_links_in_foreign_key_order(chat_client, monkeypatch):
    import main
    client, db = chat_client
    db.execute(text("PRAGMA foreign_keys=ON"))
    submit(client, linked_plan())
    submit(client, notification_plan())
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=db.get_bind()))
    deleted = main._wipe_sql()
    db.expire_all()
    assert deleted["workflows"] == 2
    assert deleted["workflow_links"] == deleted["workflow_notifications"] == 1
    assert db.query(WorkflowStepDB).count() == db.query(WorkflowDB).count() == 0
