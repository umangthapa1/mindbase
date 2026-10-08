"""Durable local workflow steps. Each effect and its result share one transaction."""
from datetime import timedelta
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Literal
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from capabilities import seed_capabilities
from database import (get_db, CapabilityDB, TaskDB, ReminderDB, WorkflowDB, WorkflowStepDB,
                      WorkflowLinkDB, WorkflowNotificationDB, WorkspaceComponentDB)
from tasks_service import task_manager
from workflow_planner import (WorkflowCreate, WorkflowPlan, TaskStep, CalendarStep, ReminderStep,
                              WaitStep, NotificationStep, step_adapter)
from workspace_planner import ReminderInputs
from workspace_runtime import _lock, utcnow, iso, event, create_reminder, reminder_action
from intent_routing import completion_claim
from component_runtime import seed_component_templates, attach_template

router = APIRouter(prefix="/api/workspace/workflows", tags=["workflows"])
MAX_FAILURES = 3


class ReminderCancelled(Exception):
    pass


def serialize_workflow(db, row):
    steps = db.query(WorkflowStepDB).filter_by(workflow_id=row.id).order_by(WorkflowStepDB.position).all()
    serialized_steps = [{"id": step.key, "action": json.loads(step.definition)["action"],
                         "status": step.status, "attempts": step.attempts, "error": step.error,
                         "next_attempt_at": iso(step.next_attempt_at), "result": json.loads(step.result)} for step in steps]
    completed = sum(step["status"] == "completed" for step in serialized_steps)
    return {"id": row.id, "component_id": row.component_id, "title": row.title, "status": row.status,
            "created_at": iso(row.created_at), "updated_at": iso(row.updated_at),
            "can_retry": row.status in {"running", "failed"} and any(step.status == "failed" for step in steps),
            "completed_steps": completed, "total_steps": len(serialized_steps),
            "progress": (completed / len(serialized_steps)) if serialized_steps else 0,
            "plan": json.loads(row.plan),
            "steps": serialized_steps}


def create_workflow(db, plan: WorkflowPlan, conversation_id=None, idempotency_key=None, now=None):
    with _lock:
        canonical = plan.model_dump_json()
        if idempotency_key:
            existing = db.query(WorkflowDB).filter_by(idempotency_key=idempotency_key).one_or_none()
            if existing:
                if existing.plan != canonical:
                    raise HTTPException(409, "This idempotency key already belongs to a different plan")
                return existing
        seed_capabilities(db)
        seed_component_templates(db)
        if not db.get(CapabilityDB, "workflows").enabled:
            raise HTTPException(409, "Enable workflows before creating a workflow")
        now = now or utcnow()
        position = db.query(func.max(WorkspaceComponentDB.position)).scalar()
        component = WorkspaceComponentDB(capability_id="workflows", kind="workflow", position=(position or 0) + 1,
                                         lifecycle="active", visible=True, updated_at=now)
        db.add(component)
        db.flush()
        row = WorkflowDB(component_id=component.id, title=plan.title, plan=canonical, conversation_id=conversation_id,
                         idempotency_key=idempotency_key, created_at=now, updated_at=now)
        db.add(row)
        db.flush()
        attach_template(db, component, "workflow-status", commit=False)
        component.props = json.dumps({"workflow_id": row.id})
        for position, step in enumerate(plan.steps):
            db.add(WorkflowStepDB(workflow_id=row.id, key=step.id, position=position, definition=step.model_dump_json()))
        event(db, "workflow.created", workflow_id=row.id)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent requests with the same key converge before any step runs.
            db.rollback()
            existing = db.query(WorkflowDB).filter_by(idempotency_key=idempotency_key).one_or_none() if idempotency_key else None
            if existing and existing.plan == canonical:
                return existing
            raise HTTPException(409, "Workflow creation conflicted; use a fresh idempotency key")
        process_workflows(db, now, workflow_id=row.id)
        return db.get(WorkflowDB, row.id)


def complete_linked_task(db, reminder_id, now=None):
    link = db.query(WorkflowLinkDB).filter_by(reminder_id=reminder_id).one_or_none()
    task = db.get(TaskDB, link.task_id) if link and link.task_id else None
    if task and task.status != "completed":
        task.status, task.updated_at = "completed", now or utcnow()
        event(db, "workflow.task_completed", reminder_id, workflow_id=link.workflow_id, task_id=task.id)


def complete_recent_workflow(db, message, history, conversation_id):
    assistant = next((turn["content"] for turn in reversed(history) if turn.get("role") == "assistant"), "")
    match = re.match(r"^(?:Created workflow|Completed workflow task|Already completed workflow task): \*\*(.+?)\*\*", assistant)
    if not match:
        return None
    unclear = {"success": False, "message": "Which workflow task did you complete? Please use the linked reminder's Done button."}
    workflows = db.query(WorkflowDB).filter(WorkflowDB.conversation_id == conversation_id,
                                           func.lower(WorkflowDB.title) == match.group(1).lower()).limit(2).all()
    if len(workflows) != 1:
        return unclear
    workflow = workflows[0]
    links = db.query(WorkflowLinkDB).filter_by(workflow_id=workflow.id).limit(2).all()
    if len(links) != 1 or not links[0].task_id or workflow.status == "cancelled":
        return unclear
    task, reminder = db.get(TaskDB, links[0].task_id), db.get(ReminderDB, links[0].reminder_id)
    if not task or not reminder or reminder.status == "cancelled":
        return unclear
    claim = completion_claim(message)
    if claim is None:
        return unclear
    if claim:
        verb, activity = claim.split(" ", 1)
        words = set(re.findall(r"\w+", activity)) - {"the", "my", "our", "just", "already", "now"}
        title_words = set(re.findall(r"\w+", task.title.lower()))
        if (verb not in title_words and verb not in {"finish", "complete"}) or not (
            activity in {"it", "this", "that", "the task"} or words & title_words
        ) or words & {"other", "another", "different"}:
            return unclear
    already = task.status == "completed"
    reminder_action(db, reminder.id, "complete")
    process_workflows(db, workflow_id=workflow.id)
    return {"action": "complete_workflow_task", "success": True, "item_type": "workflow", "item_id": workflow.id,
            "message": f"{'Already completed' if already else 'Completed'} workflow task: **{workflow.title}**"}


def sync_linked_completion(db, task_id=None, now=None):
    """Reconcile existing task updates, including the legacy scheduling handlers."""
    with _lock:
        rows = db.query(WorkflowLinkDB).join(TaskDB, TaskDB.id == WorkflowLinkDB.task_id).join(
            ReminderDB, ReminderDB.id == WorkflowLinkDB.reminder_id).filter(
            TaskDB.status == "completed", ReminderDB.status.in_(["active", "paused", "due"]))
        if task_id:
            rows = rows.filter(WorkflowLinkDB.task_id == task_id)
        for link in rows.all():
            reminder_action(db, link.reminder_id, "complete", now, commit=False)
        db.flush()


def _reference(db, workflow_id, key):
    row = db.query(WorkflowStepDB).filter_by(workflow_id=workflow_id, key=key).one()
    return json.loads(row.result)["item_id"]


def execute_step(db, workflow, row, step, now):
    if isinstance(step, TaskStep):
        task = task_manager.create_task(db, **step.inputs.model_dump(), commit=False)
        return {"item_id": task.id, "item_type": "task"}
    if isinstance(step, CalendarStep):
        item = task_manager.create_event(db, **step.inputs.model_dump(), commit=False)
        return {"item_id": item.id, "item_type": "event"}
    if isinstance(step, ReminderStep):
        reminder = create_reminder(db, ReminderInputs(**step.inputs.model_dump(exclude={"task_step_id"})),
                                   workflow.conversation_id, now, commit=False)
        if step.inputs.task_step_id:
            task_id = _reference(db, workflow.id, step.inputs.task_step_id)
            task = db.get(TaskDB, task_id)
            if not task:
                raise HTTPException(404, "The linked task was deleted")
            db.add(WorkflowLinkDB(workflow_id=workflow.id, task_id=task_id, reminder_id=reminder.id))
            db.flush()
            if task.status == "completed":
                reminder_action(db, reminder.id, "complete", now, commit=False)
        return {"item_id": reminder.id, "item_type": "reminder"}
    if isinstance(step, WaitStep):
        reminder_id = _reference(db, workflow.id, step.inputs.reminder_step_id)
        reminder = db.get(ReminderDB, reminder_id)
        if not reminder:
            raise HTTPException(404, "The workflow reminder was deleted")
        if reminder.status == "cancelled":
            raise ReminderCancelled()
        # Completing before the deadline also satisfies a 'due' wait.
        if reminder.status == "completed" or (step.inputs.until == "due" and reminder.status == "due"):
            return {"item_id": reminder.id, "item_type": "reminder"}
        return None
    if isinstance(step, NotificationStep):
        if not db.get(CapabilityDB, "notifications").enabled:
            raise HTTPException(409, "Enable notifications to run this workflow step")
        notification = WorkflowNotificationDB(workflow_id=workflow.id, step_id=row.id,
                                              message=step.inputs.message, created_at=now)
        db.add(notification)
        db.flush()
        return {"item_id": notification.id, "item_type": "notification"}
    raise ValueError("Unsupported workflow action")


def process_workflows(db, now=None, workflow_id=None):
    with _lock:
        now = now or utcnow()
        sync_linked_completion(db, now=now)
        db.commit()
        query = db.query(WorkflowDB).filter_by(status="running")
        if workflow_id:
            query = query.filter_by(id=workflow_id)
        for workflow in query.order_by(WorkflowDB.created_at).all():
            steps = db.query(WorkflowStepDB).filter_by(workflow_id=workflow.id).order_by(WorkflowStepDB.position).all()
            by_key = {row.key: row for row in steps}
            for row in steps:
                if workflow.status != "running":
                    break
                if row.status not in {"pending", "waiting", "failed"} or (row.next_attempt_at and row.next_attempt_at > now):
                    continue
                step = step_adapter.validate_json(row.definition)
                if any(by_key[key].status != "completed" for key in step.depends_on):
                    continue
                row_id, workflow_id_value, previous_status = row.id, workflow.id, row.status
                try:
                    claimed = db.query(WorkflowStepDB).filter_by(id=row.id, status=previous_status).update(
                        {"status": "running"}, synchronize_session="fetch")
                    if not claimed:
                        db.rollback()
                        continue
                    result = execute_step(db, workflow, row, step, now)
                    if previous_status != "waiting":
                        row.attempts += 1
                    row.status = "waiting" if result is None else "completed"
                    row.result, row.error, row.next_attempt_at = json.dumps(result or {}), None, None
                    row.failure_count = 0
                    workflow.updated_at = now
                    if result is not None:
                        event(db, "workflow.step_completed", workflow_id=workflow.id, step_id=row.key)
                    db.commit()  # Local side effect and its completion record are atomic.
                except ReminderCancelled:
                    db.rollback()
                    cancel_workflow(db, workflow_id_value, now)
                    break
                except Exception as exc:
                    db.rollback()
                    row, workflow = db.get(WorkflowStepDB, row_id), db.get(WorkflowDB, workflow_id_value)
                    row.attempts += 1
                    row.failure_count += 1
                    row.status = "failed"
                    row.error = str(exc.detail if isinstance(exc, HTTPException) else exc)[:500] or "Step failed"
                    row.next_attempt_at = now + timedelta(seconds=2 ** (row.failure_count - 1)) if row.failure_count < MAX_FAILURES else None
                    workflow.updated_at = now
                    event(db, "workflow.step_failed", workflow_id=workflow.id, step_id=row.key, attempt=row.attempts)
                    if row.failure_count >= MAX_FAILURES:
                        workflow.status = "failed"
                        event(db, "workflow.failed", workflow_id=workflow.id)
                    db.commit()
            if workflow.status == "running" and all(row.status == "completed" for row in steps):
                workflow.status, workflow.updated_at = "completed", now
                event(db, "workflow.completed", workflow_id=workflow.id)
                db.commit()


def cancel_workflow(db, workflow_id, now=None):
    with _lock:
        row = db.get(WorkflowDB, workflow_id)
        if not row:
            raise HTTPException(404, "Workflow not found")
        if row.status == "cancelled":
            return row
        if row.status == "completed":
            raise HTTPException(409, "Completed workflows cannot be cancelled")
        now = now or utcnow()
        steps = db.query(WorkflowStepDB).filter_by(workflow_id=row.id).all()
        for step in steps:
            if step.status != "completed":
                step.status, step.next_attempt_at = "cancelled", None
            result = json.loads(step.result)
            if result.get("item_type") == "reminder":
                reminder = db.get(ReminderDB, result["item_id"])
                if reminder and reminder.status in {"active", "paused", "due"}:
                    reminder_action(db, reminder.id, "cancel", now, commit=False)
        db.query(WorkflowNotificationDB).filter_by(workflow_id=row.id, acknowledged_at=None).update({"acknowledged_at": now})
        row.status, row.updated_at = "cancelled", now
        event(db, "workflow.cancelled", workflow_id=row.id)
        db.commit()
        return row


class WorkflowAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["retry", "cancel"]


@router.post("")
def add_workflow(request: WorkflowCreate, db=Depends(get_db)):
    return serialize_workflow(db, create_workflow(db, request.plan, idempotency_key=request.idempotency_key))


@router.get("")
def list_workflows(db=Depends(get_db)):
    return [serialize_workflow(db, row) for row in db.query(WorkflowDB).order_by(WorkflowDB.created_at.desc()).limit(100)]


@router.get("/{workflow_id}")
def get_workflow(workflow_id: str, db=Depends(get_db)):
    row = db.get(WorkflowDB, workflow_id)
    if not row:
        raise HTTPException(404, "Workflow not found")
    return serialize_workflow(db, row)


@router.post("/{workflow_id}/actions")
def act_on_workflow(workflow_id: str, request: WorkflowAction, db=Depends(get_db)):
    with _lock:
        if request.action == "cancel":
            return serialize_workflow(db, cancel_workflow(db, workflow_id))
        row = db.get(WorkflowDB, workflow_id)
        if not row:
            raise HTTPException(404, "Workflow not found")
        failed = db.query(WorkflowStepDB).filter_by(workflow_id=row.id, status="failed").all()
        if row.status not in {"running", "failed"} or not failed:
            raise HTTPException(409, "This workflow has no failed steps to retry")
        for step in failed:
            step.status, step.error, step.next_attempt_at, step.failure_count = "pending", None, None, 0
        row.status, row.updated_at = "running", utcnow()
        event(db, "workflow.retried", workflow_id=row.id)
        db.commit()
        process_workflows(db, workflow_id=row.id)
        return serialize_workflow(db, row)
