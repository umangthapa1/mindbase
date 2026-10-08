"""Developer-defined capability registry. Definitions describe bounded handlers."""
import json

from database import CapabilityDB


CORE_CAPABILITIES = {
    "tasks": {"name": "Tasks", "permissions": ["tasks.read", "tasks.write"], "handler": "task_manager"},
    "calendar": {"name": "Calendar", "permissions": ["calendar.read", "calendar.write"], "handler": "task_manager"},
    "timer": {
        "name": "Timers and reminders", "permissions": ["reminders.write", "components.write"],
        "handler": "workspace_runtime", "component": "reminder",
        "inputs": {"label": "1–200 characters", "duration_seconds": "integer, 1–31536000"},
    },
    "notifications": {"name": "In-app notifications", "permissions": ["notifications.write"], "handler": "workspace_runtime"},
    "memory": {"name": "Memory", "permissions": ["memory.read", "memory.write"], "handler": "memory_manager"},
    "workflows": {"name": "Workflows", "permissions": ["workflows.write", "components.write"],
                  "handler": "workflow_runtime", "component": "workflow"},
    "components": {"name": "Declarative components", "permissions": ["components.read", "components.write"],
                    "handler": "component_runtime", "component": "panel"},
}


def seed_capabilities(db, *, commit=True):
    # Preserve user enable/disable choices across restarts.
    for key, definition in CORE_CAPABILITIES.items():
        if db.get(CapabilityDB, key) is None:
            db.add(CapabilityDB(id=key, definition=json.dumps(definition), enabled=True))
    if commit:
        db.commit()
    else:
        db.flush()


def serialize_capability(row):
    return {"id": row.id, "enabled": row.enabled, **json.loads(row.definition)}
