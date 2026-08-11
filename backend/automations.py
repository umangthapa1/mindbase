"""Deterministic, local automation rules for newly synced email."""
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from database import AutomationRuleDB, AutomationRunDB, AutomationArtifactDB, EmailAttachmentDB, EmailDB, TaskDB

EMAIL_ACTIONS = {"save", "task", "tag", "notify"}
STOP_WORDS = {"a", "an", "and", "the", "has", "have", "with", "is", "of", "or", "email", "arrives"}


def parse_actions(raw: str) -> list[str]:
    try:
        actions = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [action for action in actions if action in EMAIL_ACTIONS]


def email_matches(rule: AutomationRuleDB, email: EmailDB) -> bool:
    """Match the condition against local email text without invoking an LLM."""
    if rule.trigger != "email" or not rule.enabled:
        return False
    condition = (rule.condition or "").strip().lower()
    if not condition:
        return True
    haystack = " ".join((email.subject or "", email.sender or "", email.body or "", email.snippet or "")).lower()
    if condition in haystack:
        return True
    tokens = [word for word in re.findall(r"[\w@.-]+", condition) if word not in STOP_WORDS]
    return bool(tokens) and all(token in haystack for token in tokens)


def _tag_from_details(details: str) -> str:
    match = re.search(r"\btag(?:\s+as|\s+with)?\s+([\w-]+)", details or "", re.I)
    return match.group(1).lower() if match else "automated"


def execute_email_rule(db: Session, rule: AutomationRuleDB, email: EmailDB) -> dict[str, Any]:
    """Execute one matching rule exactly once per email.

    The run record is committed with its effects, so a later sync cannot create a
    duplicate task for the same rule/email pair.
    """
    prior = db.query(AutomationRunDB).filter_by(rule_id=rule.id, email_id=email.id).first()
    if prior:
        return {"status": "already_processed", "result": json.loads(prior.result or "{}")}

    actions = parse_actions(rule.actions)
    result: dict[str, Any] = {"actions": []}
    run = AutomationRunDB(rule_id=rule.id, email_id=email.id, status="completed")
    db.add(run)
    db.flush()
    if "save" in actions:
        attachments = db.query(EmailAttachmentDB).filter_by(email_id=email.id).all()
        for attachment in attachments:
            db.add(AutomationArtifactDB(run_id=run.id, email_id=email.id, attachment_id=attachment.id, kind="attachment", label=attachment.filename))
        result["actions"].append({"type": "save", "saved_files": len(attachments)})
    if "task" in actions:
        task = TaskDB(
            title=f"Follow up: {email.subject or 'Untitled email'}",
            description=f"Created by automation '{rule.name}' from {email.sender or 'unknown sender'}.\n\n{(email.body or email.snippet or '')[:2000]}",
            tags="automation,email",
        )
        db.add(task)
        db.flush()
        db.add(AutomationArtifactDB(run_id=run.id, email_id=email.id, task_id=task.id, kind="task", label=task.title))
        result["actions"].append({"type": "task", "task_id": task.id})
    if "tag" in actions:
        tag = _tag_from_details(rule.details)
        existing = {value.strip() for value in (email.tags or "").split(",") if value.strip()}
        existing.add(tag)
        email.tags = ",".join(sorted(existing))
        db.add(AutomationArtifactDB(run_id=run.id, email_id=email.id, kind="tag", label=tag))
        result["actions"].append({"type": "tag", "tag": tag})
    if "notify" in actions:
        # Local notification delivery is intentionally not assumed; retain an
        # auditable event for a future notification surface instead.
        db.add(AutomationArtifactDB(run_id=run.id, email_id=email.id, kind="notification", label="Notification recorded"))
        result["actions"].append({"type": "notify", "status": "recorded"})

    run.result = json.dumps(result)
    db.commit()
    return {"status": "completed", "result": result}


def process_new_emails(db: Session, emails: list[EmailDB]) -> list[dict[str, Any]]:
    rules = db.query(AutomationRuleDB).filter_by(trigger="email", enabled=True).all()
    runs = []
    for email in emails:
        for rule in rules:
            if email_matches(rule, email):
                runs.append({"email_id": email.id, "rule_id": rule.id, **execute_email_rule(db, rule, email)})
    return runs


def serialize_rule(rule: AutomationRuleDB) -> dict[str, Any]:
    return {"id": rule.id, "name": rule.name, "trigger": rule.trigger, "condition": rule.condition,
            "actions": parse_actions(rule.actions), "details": rule.details, "enabled": bool(rule.enabled),
            "created_at": rule.created_at.isoformat(), "updated_at": rule.updated_at.isoformat()}


def serialize_run(run: AutomationRunDB, db: Session) -> dict[str, Any]:
    email = db.query(EmailDB).filter_by(id=run.email_id).first()
    rule = db.query(AutomationRuleDB).filter_by(id=run.rule_id).first()
    artifacts = db.query(AutomationArtifactDB).filter_by(run_id=run.id).all()
    return {"id": run.id, "status": run.status, "created_at": run.created_at.isoformat(),
            "rule": {"id": rule.id, "name": rule.name} if rule else None,
            "email": {"id": email.id, "subject": email.subject, "sender": email.sender} if email else None,
            "artifacts": [{"id": artifact.id, "kind": artifact.kind, "label": artifact.label,
                           "attachment_id": artifact.attachment_id, "task_id": artifact.task_id} for artifact in artifacts]}
