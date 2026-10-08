"""Versioned declarative workspace components.

Definitions are data-only and intentionally small. Every type, binding, action, and
permission is allowlisted here; the browser never evaluates a template definition.
"""
from datetime import datetime
import json
import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func

from capabilities import seed_capabilities
from database import (get_db, WorkspaceComponentDB, WorkspaceTemplateDB,
                      WorkspaceTemplateVersionDB, WorkflowDB)
from workspace_runtime import _lock, event, iso, utcnow

router = APIRouter(prefix="/api/workspace", tags=["workspace components"])

MAX_DEFINITION_BYTES = 16_384
MAX_INSTANCE_DATA_BYTES = 12_288
TEMPLATE_VERSION = 1
KEY = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")]
READ_PERMISSIONS = {"tasks.read", "calendar.read", "reminders.read", "workflows.read", "notifications.read", "components.read"}
WRITE_PERMISSIONS = {"tasks.write", "calendar.write", "reminders.write", "workflows.write", "notifications.write"}
ALL_PERMISSIONS = READ_PERMISSIONS | WRITE_PERMISSIONS
NODE_TYPES = {"text", "status", "progress", "list"}
SOURCES = {"title", "label", "status", "message", "steps", "completed_steps", "total_steps", "progress"}
ACTION_NAMES = {"retry", "cancel", "pause", "resume", "complete"}


class DeclarativeNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: KEY
    type: Literal["text", "status", "progress", "list"]
    label: str = Field(default="", max_length=120)
    source: Literal["title", "label", "status", "message", "steps", "completed_steps", "total_steps", "progress"]


class DeclarativeAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: KEY
    label: str = Field(min_length=1, max_length=80)
    action: Literal["retry", "cancel", "pause", "resume", "complete"]
    permission: str

    @field_validator("permission")
    @classmethod
    def valid_permission(cls, value):
        if value not in ALL_PERMISSIONS:
            raise ValueError("Unknown component permission")
        return value


class TemplateDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = TEMPLATE_VERSION
    layout: Literal["stack", "grid"] = "stack"
    permissions: list[str] = Field(default_factory=list, max_length=12)
    nodes: list[DeclarativeNode] = Field(min_length=1, max_length=12)
    actions: list[DeclarativeAction] = Field(default_factory=list, max_length=8)

    @field_validator("permissions")
    @classmethod
    def valid_permissions(cls, values):
        if len(set(values)) != len(values) or any(value not in ALL_PERMISSIONS for value in values):
            raise ValueError("Unknown or duplicate component permission")
        return values

    @model_validator(mode="after")
    def validate_bindings(self):
        if len({node.id for node in self.nodes}) != len(self.nodes):
            raise ValueError("Component node IDs must be unique")
        if len({action.id for action in self.actions}) != len(self.actions):
            raise ValueError("Component action IDs must be unique")
        for action in self.actions:
            if action.permission not in self.permissions:
                raise ValueError("Every action permission must be declared by the template")
        for node in self.nodes:
            if node.type == "list" and node.source != "steps":
                raise ValueError("List nodes may only bind to workflow steps")
            if node.type == "progress" and node.source != "progress":
                raise ValueError("Progress nodes must bind to progress")
        return self


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: KEY
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    definition: TemplateDefinition


class TemplateVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: TemplateDefinition


class InstanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_version: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, max_length=200)
    data: dict[str, Any] = Field(default_factory=dict)
    workflow_id: str | None = None

    @model_validator(mode="after")
    def bounded_data(self):
        if len(json.dumps(self.data, separators=(",", ":"), default=str)) > MAX_INSTANCE_DATA_BYTES:
            raise ValueError("Component data is too large")
        return self


class ComponentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["archive", "restore", "upgrade"]


class TemplateStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "archived"]


def _definition_json(definition: TemplateDefinition) -> str:
    encoded = definition.model_dump_json()
    if len(encoded.encode("utf-8")) > MAX_DEFINITION_BYTES:
        raise HTTPException(422, "Template definition is too large")
    return encoded


def serialize_definition(row):
    return json.loads(row.definition)


def serialize_version(row):
    return {"id": row.id, "version": row.version, "definition": serialize_definition(row), "created_at": iso(row.created_at)}


def serialize_template(db, row, *, include_versions=False):
    result = {"id": row.id, "name": row.name, "description": row.description or "", "status": row.status,
              "current_version": row.current_version, "created_at": iso(row.created_at), "updated_at": iso(row.updated_at)}
    current = db.query(WorkspaceTemplateVersionDB).filter_by(template_id=row.id, version=row.current_version).one_or_none()
    if current:
        result["current"] = serialize_version(current)
    if include_versions:
        result["versions"] = [serialize_version(version) for version in db.query(WorkspaceTemplateVersionDB)
                               .filter_by(template_id=row.id).order_by(WorkspaceTemplateVersionDB.version)]
    return result


def get_template_version(db, template_id, version=None):
    template = db.get(WorkspaceTemplateDB, template_id)
    if not template:
        raise HTTPException(404, "Workspace template not found")
    version = version or template.current_version
    row = db.query(WorkspaceTemplateVersionDB).filter_by(template_id=template.id, version=version).one_or_none()
    if not row:
        raise HTTPException(404, "Workspace template version not found")
    return template, row


def seed_component_templates(db, *, commit=True):
    """Create the built-in workflow panel once; existing instances stay pinned."""
    definition = TemplateDefinition(
        layout="stack",
        permissions=["workflows.read", "workflows.write"],
        nodes=[
            {"id": "title", "type": "text", "source": "title"},
            {"id": "status", "type": "status", "source": "status"},
            {"id": "progress", "type": "progress", "source": "progress"},
            {"id": "steps", "type": "list", "source": "steps"},
        ],
        actions=[
            {"id": "retry", "label": "Retry failed steps", "action": "retry", "permission": "workflows.write"},
            {"id": "cancel", "label": "Cancel workflow", "action": "cancel", "permission": "workflows.write"},
        ],
    )
    template = db.get(WorkspaceTemplateDB, "workflow-status")
    if not template:
        now = utcnow()
        template = WorkspaceTemplateDB(id="workflow-status", name="Workflow status",
                                       description="A safe status panel for a local workflow.",
                                       current_version=1, created_at=now, updated_at=now)
        db.add(template)
        db.flush()
        db.add(WorkspaceTemplateVersionDB(template_id=template.id, version=1, definition=_definition_json(definition), created_at=now))
    if commit:
        db.commit()
    else:
        db.flush()
    return template


def attach_template(db, component, template_id, version=None, *, commit=False):
    template, version_row = get_template_version(db, template_id, version)
    component.template_id, component.template_version = template.id, version_row.version
    component.updated_at = utcnow()
    if commit:
        db.commit()
    else:
        db.flush()
    return template, version_row


def serialize_component_template(db, component):
    if not component.template_id:
        return None
    template, version = get_template_version(db, component.template_id, component.template_version)
    return {"id": template.id, "name": template.name, "version": version.version,
            "definition": serialize_definition(version), "current_version": template.current_version,
            "can_upgrade": version.version < template.current_version,
            "status": template.status, "source_extension_id": template.source_extension_id,
            "source_extension_version": template.source_extension_version}


def component_lifecycle(db, component, action):
    now = utcnow()
    if action == "archive":
        component.lifecycle, component.visible = "archived", False
    elif action == "restore":
        component.lifecycle, component.visible = "active", True
    elif action == "upgrade":
        if not component.template_id:
            raise HTTPException(409, "This component has no versioned template")
        template, current = get_template_version(db, component.template_id)
        if template.status != "active":
            raise HTTPException(409, "The template is archived")
        if current.version == component.template_version:
            return component
        component.template_version = current.version
    component.updated_at = now
    event(db, f"component.{action}", component_id=component.id, template_id=component.template_id,
          template_version=component.template_version)
    db.commit()
    return component


@router.post("/templates")
def create_template(request: TemplateCreate, db=Depends(get_db)):
    with _lock:
        if db.get(WorkspaceTemplateDB, request.id):
            raise HTTPException(409, "Template ID already exists")
        now = utcnow()
        row = WorkspaceTemplateDB(id=request.id, name=request.name, description=request.description,
                                  current_version=1, created_at=now, updated_at=now)
        db.add(row)
        db.flush()
        db.add(WorkspaceTemplateVersionDB(template_id=row.id, version=1,
                                          definition=_definition_json(request.definition), created_at=now))
        event(db, "template.created", template_id=row.id, version=1)
        db.commit()
        return serialize_template(db, row, include_versions=True)


@router.get("/templates")
def list_templates(db=Depends(get_db)):
    seed_capabilities(db)
    seed_component_templates(db)
    return [serialize_template(db, row) for row in db.query(WorkspaceTemplateDB).order_by(WorkspaceTemplateDB.name)]


@router.get("/templates/{template_id}")
def get_template(template_id: str, db=Depends(get_db)):
    seed_component_templates(db)
    row = db.get(WorkspaceTemplateDB, template_id)
    if not row:
        raise HTTPException(404, "Workspace template not found")
    return serialize_template(db, row, include_versions=True)


@router.post("/templates/{template_id}/versions")
def add_template_version(template_id: str, request: TemplateVersionCreate, db=Depends(get_db)):
    with _lock:
        template = db.get(WorkspaceTemplateDB, template_id)
        if not template:
            raise HTTPException(404, "Workspace template not found")
        if template.status != "active":
            raise HTTPException(409, "Archived templates cannot receive new versions")
        version = template.current_version + 1
        now = utcnow()
        row = WorkspaceTemplateVersionDB(template_id=template.id, version=version,
                                         definition=_definition_json(request.definition), created_at=now)
        db.add(row)
        template.current_version, template.updated_at = version, now
        event(db, "template.version_created", template_id=template.id, version=version)
        db.commit()
        return serialize_template(db, template, include_versions=True)


@router.patch("/templates/{template_id}")
def update_template(template_id: str, request: TemplateStatusUpdate, db=Depends(get_db)):
    with _lock:
        template = db.get(WorkspaceTemplateDB, template_id)
        if not template:
            raise HTTPException(404, "Workspace template not found")
        template.status, template.updated_at = request.status, utcnow()
        event(db, "template.updated", template_id=template.id, status=template.status)
        db.commit()
        return serialize_template(db, template, include_versions=True)


@router.post("/templates/{template_id}/instances")
def instantiate_template(template_id: str, request: InstanceCreate, db=Depends(get_db)):
    with _lock:
        seed_capabilities(db)
        template, version = get_template_version(db, template_id, request.template_version)
        if template.status != "active":
            raise HTTPException(409, "Archived templates cannot create instances")
        if request.workflow_id and not db.get(WorkflowDB, request.workflow_id):
            raise HTTPException(404, "Workflow not found")
        position = db.query(func.max(WorkspaceComponentDB.position)).scalar()
        component = WorkspaceComponentDB(capability_id="components", kind="panel", position=(position or 0) + 1,
                                         props=json.dumps({**request.data, **({"workflow_id": request.workflow_id} if request.workflow_id else {})}),
                                         template_id=template.id, template_version=version.version,
                                         lifecycle="active", visible=True, updated_at=utcnow())
        db.add(component)
        db.flush()
        event(db, "component.created", component_id=component.id, template_id=template.id, template_version=version.version)
        db.commit()
        return {"component": component.id, "template": serialize_component_template(db, component)}


@router.post("/components/{component_id}/actions")
def act_on_component(component_id: str, request: ComponentAction, db=Depends(get_db)):
    with _lock:
        component = db.get(WorkspaceComponentDB, component_id)
        if not component:
            raise HTTPException(404, "Component not found")
        component_lifecycle(db, component, request.action)
        return {"id": component.id, "lifecycle": component.lifecycle, "visible": component.visible,
                "template": serialize_component_template(db, component)}
