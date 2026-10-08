"""Persistent bounded runtime. Deadlines, not browser intervals, own timer state."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import re
import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Literal
from sqlalchemy import func

from capabilities import seed_capabilities, serialize_capability
from database import (get_db, SessionLocal, CapabilityDB, WorkspaceComponentDB,
                      ReminderDB, WorkspaceEventDB, WorkspaceNotificationDB, WorkflowDB,
                      WorkflowLinkDB, WorkflowNotificationDB)
from workspace_planner import ReminderInputs
from intent_routing import completion_claim

router = APIRouter(prefix="/api", tags=["workspace runtime"])
_lock = threading.RLock()
logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(value):
    return value.isoformat(timespec="milliseconds") + "Z" if value else None


def event(db, kind, reminder_id=None, **payload):
    db.add(WorkspaceEventDB(type=kind, reminder_id=reminder_id, payload=json.dumps(payload)))


def serialize_reminder(row, now=None):
    now = now or utcnow()
    remaining = max(0, (row.due_at - now).total_seconds()) if row.status == "active" else row.remaining_seconds
    return {"id": row.id, "component_id": row.component_id, "label": row.label,
            "status": row.status, "due_at": iso(row.due_at), "remaining_seconds": remaining}


def serialize_component(db, row):
    # Derive live props from the reminder: no stale copy of the resumed deadline.
    reminder = db.query(ReminderDB).filter_by(component_id=row.id).one_or_none()
    props = json.loads(row.props)
    if reminder:
        props.update(serialize_reminder(reminder))
        link = db.query(WorkflowLinkDB).filter_by(reminder_id=reminder.id).one_or_none()
        if link:
            props.update(task_id=link.task_id, workflow_id=link.workflow_id)
    if row.kind == "workflow":
        from workflow_runtime import serialize_workflow
        workflow = db.query(WorkflowDB).filter_by(component_id=row.id).one_or_none()
        if workflow:
            props.update(serialize_workflow(db, workflow))
            props["label"] = workflow.title
    template = None
    if row.template_id:
        from component_runtime import serialize_component_template
        template = serialize_component_template(db, row)
    return {"id": row.id, "capability_id": row.capability_id, "kind": row.kind,
            "position": row.position, "visible": row.visible, "lifecycle": row.lifecycle,
            "props": props, "template": template}


def create_reminder(db, inputs: ReminderInputs, conversation_id=None, now=None, *, commit=True):
    with _lock:
        seed_capabilities(db, commit=commit)
        if any(not db.get(CapabilityDB, key).enabled for key in ("timer", "notifications")):
            raise HTTPException(409, "Enable timers and notifications before creating a reminder.")
        now = now or utcnow()
        position = db.query(func.max(WorkspaceComponentDB.position)).scalar()
        component = WorkspaceComponentDB(capability_id="timer", kind="reminder", position=(position or 0) + 1)
        db.add(component)
        db.flush()
        reminder = ReminderDB(component_id=component.id, conversation_id=conversation_id,
                              label=inputs.label.strip(), due_at=now + timedelta(seconds=inputs.duration_seconds),
                              remaining_seconds=inputs.duration_seconds, created_at=now, updated_at=now)
        db.add(reminder)
        db.flush()
        event(db, "reminder.created", reminder.id, component_id=component.id, conversation_id=conversation_id)
        if commit:
            db.commit()
        else:
            db.flush()
        return reminder


def process_due(db, now=None, *, commit=True):
    """Claim each overdue active row atomically; repeated ticks/restarts don't redeliver."""
    with _lock:
        now = now or utcnow()
        rows = db.query(ReminderDB).filter(ReminderDB.status == "active", ReminderDB.due_at <= now).all()
        for row in rows:
            claimed = db.query(ReminderDB).filter(ReminderDB.id == row.id, ReminderDB.status == "active",
                                                  ReminderDB.due_at <= now).update(
                {"status": "due", "remaining_seconds": 0, "updated_at": now}, synchronize_session="fetch")
            if claimed:
                db.add(WorkspaceNotificationDB(reminder_id=row.id, message=f"Reminder: {row.label}", created_at=now))
                event(db, "reminder.due", row.id)
        if commit:
            db.commit()
            db.expire_all()
        else:
            db.flush()


def reminder_action(db, reminder_id, action, now=None, *, commit=True):
    with _lock:
        now = now or utcnow()
        if action in {"pause", "resume"}:
            process_due(db, now, commit=commit)
        row = db.get(ReminderDB, reminder_id)
        if not row:
            raise HTTPException(404, "Reminder not found")
        if action == "pause" and row.status == "active":
            row.remaining_seconds = max(0, (row.due_at - now).total_seconds())
            row.due_at, row.status = None, "paused"
        elif action == "resume" and row.status == "paused":
            row.due_at, row.status = now + timedelta(seconds=row.remaining_seconds), "active"
        elif action in {"complete", "cancel"} and row.status in {"active", "paused", "due"}:
            row.status = "completed" if action == "complete" else "cancelled"
            row.remaining_seconds = 0
            # Suppress still-undelivered alerts when the user explicitly finishes/cancels.
            db.query(WorkspaceNotificationDB).filter_by(reminder_id=row.id, acknowledged_at=None).update(
                {"acknowledged_at": now})
        elif (action, row.status) in {("pause", "paused"), ("resume", "active"),
                                      ("complete", "completed"), ("cancel", "cancelled")}:
            return row
        else:
            raise HTTPException(409, f"Cannot {action} a {row.status} reminder")
        row.updated_at = now
        if row.status == "completed":
            from workflow_runtime import complete_linked_task
            complete_linked_task(db, row.id, now)
        event(db, f"reminder.{row.status}", row.id)
        if commit:
            db.commit()
        else:
            db.flush()
        return row


def tick_once():
    from workflow_runtime import sync_linked_completion, process_workflows
    with SessionLocal() as db:
        with _lock:
            sync_linked_completion(db)
            process_due(db)
            process_workflows(db)


def complete_recent_reminder(db, message, history, conversation_id):
    """Resolve only the latest assistant reference, never skip to an older reminder."""
    assistant = next((turn["content"] for turn in reversed(history) if turn.get("role") == "assistant"), "")
    match = re.match(r"^(?:Created|Completed|Already completed) reminder: \*\*(.+?)\*\*", assistant)
    if not match:
        return None
    unclear = {"success": False, "message": "Which reminder did you complete? Please use its Done button."}
    matches = db.query(ReminderDB).filter(ReminderDB.conversation_id == conversation_id,
                                         func.lower(ReminderDB.label) == match.group(1).lower()).limit(2).all()
    if len(matches) != 1:
        return unclear
    row = matches[0]
    claim = completion_claim(message)
    if claim is None:
        return unclear
    if claim:
        verb, activity = claim.split(" ", 1)
        words = set(re.findall(r"\w+", activity.lower())) - {"the", "my", "our", "just", "already", "now"}
        title_words = set(re.findall(r"\w+", row.label.lower()))
        if (verb not in title_words and verb not in {"finish", "complete"}) or not (
            activity in {"it", "this", "that", "the reminder"} or words & title_words
        ) or words & {"other", "another", "different"}:
            return unclear
    if row.status == "cancelled":
        return unclear
    already = row.status == "completed"
    reminder_action(db, row.id, "complete")
    return {"action": "complete_reminder", "success": True, "item_id": row.id, "item_type": "reminder",
            "message": f"{'Already completed' if already else 'Completed'} reminder: **{row.label}**"}


async def runtime_loop():
    while True:
        try:
            await asyncio.to_thread(tick_once)
        except Exception:
            logger.exception("Reminder tick failed; retrying on next tick")
        await asyncio.sleep(1)


class EnabledUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class ReminderAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "complete", "cancel"]


class ComponentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visible: bool | None = None
    move: Literal["earlier", "later"] | None = None


@router.get("/capabilities")
def list_capabilities(db=Depends(get_db)):
    with _lock:
        seed_capabilities(db)
        return [serialize_capability(row) for row in db.query(CapabilityDB).order_by(CapabilityDB.id)]


@router.patch("/capabilities/{capability_id}")
def update_capability(capability_id: str, request: EnabledUpdate, db=Depends(get_db)):
    with _lock:
        seed_capabilities(db)
        row = db.get(CapabilityDB, capability_id)
        if not row:
            raise HTTPException(404, "Capability not found")
        if capability_id not in {"timer", "notifications", "workflows"}:
            raise HTTPException(409, "Only timer, notification, and workflow capabilities are configurable.")
        row.enabled = request.enabled
        event(db, "capability.updated", capability_id=capability_id, enabled=row.enabled)
        db.commit()
        return serialize_capability(row)


@router.post("/workspace/reminders")
def add_reminder(request: ReminderInputs, db=Depends(get_db)):
    return serialize_reminder(create_reminder(db, request))


@router.get("/workspace/reminders")
def list_reminders(db=Depends(get_db)):
    return [serialize_reminder(row) for row in db.query(ReminderDB).order_by(ReminderDB.created_at, ReminderDB.id)]


@router.post("/workspace/reminders/{reminder_id}/actions")
def act_on_reminder(reminder_id: str, request: ReminderAction, db=Depends(get_db)):
    from workflow_runtime import process_workflows
    row = reminder_action(db, reminder_id, request.action)
    process_workflows(db)
    return serialize_reminder(row)


@router.get("/workspace/components")
def list_components(db=Depends(get_db)):
    return [serialize_component(db, row) for row in db.query(WorkspaceComponentDB).order_by(
        WorkspaceComponentDB.position, WorkspaceComponentDB.created_at, WorkspaceComponentDB.id)]


@router.patch("/workspace/components/{component_id}")
def update_component(component_id: str, request: ComponentUpdate, db=Depends(get_db)):
    with _lock:
        row = db.get(WorkspaceComponentDB, component_id)
        if not row:
            raise HTTPException(404, "Component not found")
        if request.visible is not None:
            row.visible = request.visible
        if request.move:
            rows = db.query(WorkspaceComponentDB).filter_by(visible=True).order_by(
                WorkspaceComponentDB.position, WorkspaceComponentDB.created_at, WorkspaceComponentDB.id).all()
            if row not in rows:
                raise HTTPException(409, "Show this component before moving it")
            index = rows.index(row)
            target = index + (-1 if request.move == "earlier" else 1)
            if 0 <= target < len(rows):
                neighbor = rows[target]
                row.position, neighbor.position = neighbor.position, row.position
        event(db, "component.updated", component_id=row.id, visible=row.visible, move=request.move)
        db.commit()
        return serialize_component(db, row)


@router.get("/workspace/events")
def list_events(db=Depends(get_db)):
    rows = db.query(WorkspaceEventDB).order_by(WorkspaceEventDB.created_at.desc(), WorkspaceEventDB.id).limit(100).all()
    return [{"id": row.id, "type": row.type, "reminder_id": row.reminder_id,
             "payload": json.loads(row.payload), "created_at": iso(row.created_at)} for row in rows]


@router.get("/workspace/notifications")
def list_notifications(db=Depends(get_db)):
    # Reads are non-consuming. Only an explicit acknowledgement changes delivery state.
    rows = db.query(WorkspaceNotificationDB).filter_by(acknowledged_at=None).order_by(
        WorkspaceNotificationDB.created_at, WorkspaceNotificationDB.id).limit(100).all()
    workflow_rows = db.query(WorkflowNotificationDB).filter_by(acknowledged_at=None).order_by(
        WorkflowNotificationDB.created_at, WorkflowNotificationDB.id).limit(100).all()
    notifications = [{"id": row.id, "reminder_id": row.reminder_id, "message": row.message,
                      "created_at": iso(row.created_at)} for row in rows]
    notifications.extend({"id": row.id, "workflow_id": row.workflow_id, "message": row.message,
                          "created_at": iso(row.created_at)} for row in workflow_rows)
    return sorted(notifications, key=lambda row: (row["created_at"], row["id"]))[:100]


@router.post("/workspace/notifications/{notification_id}/ack")
def acknowledge_notification(notification_id: str, db=Depends(get_db)):
    with _lock:
        row = db.get(WorkspaceNotificationDB, notification_id) or db.get(WorkflowNotificationDB, notification_id)
        if not row:
            raise HTTPException(404, "Notification not found")
        if row.acknowledged_at is None:
            row.acknowledged_at = utcnow()
            event(db, "notification.acknowledged", getattr(row, "reminder_id", None), notification_id=row.id,
                  **({"workflow_id": row.workflow_id} if isinstance(row, WorkflowNotificationDB) else {}))
            db.commit()
        return {"id": row.id, "acknowledged_at": iso(row.acknowledged_at)}
