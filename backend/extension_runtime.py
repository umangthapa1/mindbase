"""Phase 4: signed-by-storage, declarative extension packs with explicit grants.

An extension pack is data only. It may contribute validated workflow/template definitions,
but it has no entrypoint, module, URL, shell, Python, JavaScript, or arbitrary handler hook.
"""
from hashlib import sha256
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func

from capabilities import seed_capabilities
from component_runtime import (ALL_PERMISSIONS, TemplateDefinition, get_template_version,
                               serialize_template, seed_component_templates)
from database import (get_db, ExtensionDB, ExtensionReleaseDB, ExtensionAuditDB,
                      WorkspaceTemplateDB, WorkspaceTemplateVersionDB)
from workflow_planner import Key, WorkflowPlan
from workflow_runtime import create_workflow, serialize_workflow
from workspace_runtime import _lock, iso, utcnow, event

router = APIRouter(prefix="/api/workspace/extensions", tags=["extensions"])
EXTENSION_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 64_000


class ExtensionTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Key
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    definition: TemplateDefinition


class ExtensionWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Key
    name: str = Field(min_length=1, max_length=120)
    plan: WorkflowPlan


class ExtensionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = EXTENSION_SCHEMA_VERSION
    id: Key
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    permissions: list[str] = Field(default_factory=list, max_length=20)
    templates: list[ExtensionTemplate] = Field(default_factory=list, max_length=20)
    workflows: list[ExtensionWorkflow] = Field(default_factory=list, max_length=20)

    @field_validator("permissions")
    @classmethod
    def valid_permissions(cls, values):
        if len(set(values)) != len(values) or any(value not in ALL_PERMISSIONS for value in values):
            raise ValueError("Unknown or duplicate extension permission")
        return values

    @model_validator(mode="after")
    def validate_pack(self):
        if not self.templates and not self.workflows:
            raise ValueError("An extension must contribute at least one template or workflow")
        if len({item.id for item in self.templates}) != len(self.templates):
            raise ValueError("Extension template IDs must be unique")
        if len({item.id for item in self.workflows}) != len(self.workflows):
            raise ValueError("Extension workflow IDs must be unique")
        declared = set(self.permissions)
        for item in self.templates:
            if not set(item.definition.permissions) <= declared:
                raise ValueError("Template permissions must be declared by the extension")
        required = set()
        for item in self.workflows:
            for step in item.plan.steps:
                required.add({
                    "create_task": "tasks.write", "create_calendar_event": "calendar.write",
                    "create_reminder": "reminders.write", "wait_for_reminder": "reminders.read",
                    "notify": "notifications.write",
                }[step.action])
            required.add("workflows.write")
        if not required <= declared:
            missing = sorted(required - declared)
            raise ValueError(f"Workflow permissions are not declared: {', '.join(missing)}")
        return self


class ExtensionInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest: ExtensionManifest
    grant_permissions: list[str] = Field(default_factory=list, max_length=20)


class ExtensionReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest: ExtensionManifest
    grant_permissions: list[str] = Field(default_factory=list, max_length=20)


class ExtensionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["enable", "disable", "rollback", "uninstall"]
    version: int | None = Field(default=None, ge=1)


class ExtensionWorkflowRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=100)
    conversation_id: str | None = None


def manifest_json(manifest: ExtensionManifest) -> str:
    encoded = json.dumps(manifest.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise HTTPException(422, "Extension manifest is too large")
    return encoded


def digest(encoded: str) -> str:
    return sha256(encoded.encode("utf-8")).hexdigest()


def extension_template_id(extension_id, key):
    return f"extension--{extension_id}--{key}"


def extension_manifest(row):
    return ExtensionManifest.model_validate_json(row.manifest)


def audit(db, extension_id, action, version=None, **detail):
    db.add(ExtensionAuditDB(extension_id=extension_id, version=version, action=action, detail=json.dumps(detail)))


def permission_grants(manifest, grants):
    grant_set = set(grants)
    if len(grant_set) != len(grants) or not grant_set <= ALL_PERMISSIONS:
        raise HTTPException(422, "Extension grant contains an unknown or duplicate permission")
    missing = sorted(set(manifest.permissions) - grant_set)
    if missing:
        raise HTTPException(403, f"Explicit permission grant required: {', '.join(missing)}")
    return grant_set


def _apply_templates(db, extension, manifest, release_version):
    """Materialize pack templates into the Phase 3 registry, preserving old versions."""
    seen = set()
    for spec in manifest.templates:
        template_id = extension_template_id(extension.id, spec.id)
        seen.add(template_id)
        template = db.get(WorkspaceTemplateDB, template_id)
        definition = spec.definition.model_dump_json()
        if not template:
            now = utcnow()
            template = WorkspaceTemplateDB(id=template_id, name=spec.name, description=spec.description,
                                           current_version=1, source_extension_id=extension.id,
                                           source_extension_version=release_version, status="active",
                                           created_at=now, updated_at=now)
            db.add(template)
            db.flush()
            db.add(WorkspaceTemplateVersionDB(template_id=template.id, version=1, definition=definition, created_at=now))
        else:
            current = db.query(WorkspaceTemplateVersionDB).filter_by(template_id=template.id,
                                                                       version=template.current_version).one()
            if current.definition != definition or template.source_extension_version != release_version:
                version = template.current_version + 1
                db.add(WorkspaceTemplateVersionDB(template_id=template.id, version=version,
                                                  definition=definition, created_at=utcnow()))
                template.current_version = version
            template.name, template.description, template.status = spec.name, spec.description, "active"
            template.source_extension_id, template.source_extension_version = extension.id, release_version
            template.updated_at = utcnow()
    # Removed templates are disabled but their old versions and pinned instances remain readable.
    for template in db.query(WorkspaceTemplateDB).filter_by(source_extension_id=extension.id).all():
        if template.id not in seen:
            template.status, template.updated_at = "archived", utcnow()


def _set_pack_templates_status(db, extension_id, status):
    for template in db.query(WorkspaceTemplateDB).filter_by(source_extension_id=extension_id).all():
        template.status, template.updated_at = status, utcnow()


def serialize_extension(db, extension, *, include_audit=False):
    releases = db.query(ExtensionReleaseDB).filter_by(extension_id=extension.id).order_by(ExtensionReleaseDB.version).all()
    active = next((release for release in releases if release.version == extension.active_version), None)
    result = {"id": extension.id, "name": extension.name, "description": extension.description or "",
              "status": extension.status, "active_version": extension.active_version,
              "granted_permissions": json.loads(extension.granted_permissions),
              "created_at": iso(extension.created_at), "updated_at": iso(extension.updated_at),
              "releases": [{"version": release.version, "digest": release.digest, "status": release.status,
                            "created_at": iso(release.created_at)} for release in releases]}
    if active:
        manifest = extension_manifest(active)
        result["manifest"] = manifest.model_dump(mode="json")
        result["templates"] = [{"id": extension_template_id(extension.id, item.id), "key": item.id,
                                 "name": item.name} for item in manifest.templates]
        result["workflows"] = [{"id": item.id, "name": item.name} for item in manifest.workflows]
    if include_audit:
        result["audit"] = [{"action": row.action, "version": row.version, "detail": json.loads(row.detail),
                             "created_at": iso(row.created_at)} for row in db.query(ExtensionAuditDB)
                            .filter_by(extension_id=extension.id).order_by(ExtensionAuditDB.created_at, ExtensionAuditDB.id)]
    return result


def install_extension(db, request: ExtensionInstallRequest):
    manifest = request.manifest
    if db.get(ExtensionDB, manifest.id):
        raise HTTPException(409, "Extension ID already exists")
    grants = permission_grants(manifest, request.grant_permissions)
    encoded = manifest_json(manifest)
    now = utcnow()
    extension = ExtensionDB(id=manifest.id, name=manifest.name, description=manifest.description,
                            status="active", active_version=1, granted_permissions=json.dumps(sorted(grants)),
                            created_at=now, updated_at=now)
    db.add(extension)
    db.flush()
    db.add(ExtensionReleaseDB(extension_id=extension.id, version=1, manifest=encoded,
                              digest=digest(encoded), status="active", created_at=now))
    _apply_templates(db, extension, manifest, 1)
    audit(db, extension.id, "installed", 1, digest=digest(encoded), permissions=sorted(grants))
    db.commit()
    return extension


def add_release(db, extension, request: ExtensionReleaseRequest):
    if extension.status == "uninstalled":
        raise HTTPException(409, "Uninstalled extensions cannot receive releases")
    if request.manifest.id != extension.id:
        raise HTTPException(422, "Release manifest ID must match the extension")
    grants = set(json.loads(extension.granted_permissions))
    grants.update(permission_grants(request.manifest, request.grant_permissions))
    encoded = manifest_json(request.manifest)
    version = db.query(func.max(ExtensionReleaseDB.version)).filter_by(extension_id=extension.id).scalar() or 0
    version += 1
    now = utcnow()
    db.query(ExtensionReleaseDB).filter_by(extension_id=extension.id, status="active").update({"status": "superseded"})
    db.add(ExtensionReleaseDB(extension_id=extension.id, version=version, manifest=encoded,
                              digest=digest(encoded), status="active", created_at=now))
    extension.name, extension.description, extension.active_version = request.manifest.name, request.manifest.description, version
    extension.granted_permissions, extension.status, extension.updated_at = json.dumps(sorted(grants)), "active", now
    _apply_templates(db, extension, request.manifest, version)
    audit(db, extension.id, "release_added", version, digest=digest(encoded), permissions=sorted(grants))
    db.commit()
    return extension


def action_extension(db, extension, request: ExtensionAction):
    now = utcnow()
    if request.action == "disable":
        extension.status = "disabled"
        _set_pack_templates_status(db, extension.id, "archived")
    elif request.action == "enable":
        if extension.status == "uninstalled":
            raise HTTPException(409, "Uninstalled extensions cannot be enabled")
        release = db.query(ExtensionReleaseDB).filter_by(extension_id=extension.id, version=extension.active_version).one_or_none()
        if not release:
            raise HTTPException(409, "The active extension release is missing")
        extension.status = "active"
        _apply_templates(db, extension, extension_manifest(release), release.version)
    elif request.action == "rollback":
        if request.version is None:
            raise HTTPException(422, "Rollback requires a release version")
        release = db.query(ExtensionReleaseDB).filter_by(extension_id=extension.id, version=request.version).one_or_none()
        if not release:
            raise HTTPException(404, "Extension release not found")
        if extension.status == "uninstalled":
            raise HTTPException(409, "Uninstalled extensions cannot be rolled back")
        db.query(ExtensionReleaseDB).filter_by(extension_id=extension.id, status="active").update({"status": "superseded"})
        release.status, extension.active_version, extension.status = "active", release.version, "active"
        _apply_templates(db, extension, extension_manifest(release), release.version)
    elif request.action == "uninstall":
        extension.status = "uninstalled"
        _set_pack_templates_status(db, extension.id, "archived")
    extension.updated_at = now
    audit(db, extension.id, request.action, extension.active_version, status=extension.status)
    db.commit()
    return extension


@router.post("")
def install(request: ExtensionInstallRequest, db=Depends(get_db)):
    with _lock:
        return serialize_extension(db, install_extension(db, request), include_audit=True)


@router.get("")
def list_extensions(db=Depends(get_db)):
    return [serialize_extension(db, row) for row in db.query(ExtensionDB).order_by(ExtensionDB.name)]


@router.get("/{extension_id}")
def get_extension(extension_id: str, db=Depends(get_db)):
    row = db.get(ExtensionDB, extension_id)
    if not row:
        raise HTTPException(404, "Extension not found")
    return serialize_extension(db, row, include_audit=True)


@router.post("/{extension_id}/versions")
def release(extension_id: str, request: ExtensionReleaseRequest, db=Depends(get_db)):
    with _lock:
        row = db.get(ExtensionDB, extension_id)
        if not row:
            raise HTTPException(404, "Extension not found")
        return serialize_extension(db, add_release(db, row, request), include_audit=True)


@router.post("/{extension_id}/actions")
def act(extension_id: str, request: ExtensionAction, db=Depends(get_db)):
    with _lock:
        row = db.get(ExtensionDB, extension_id)
        if not row:
            raise HTTPException(404, "Extension not found")
        return serialize_extension(db, action_extension(db, row, request), include_audit=True)


@router.post("/{extension_id}/workflows/{workflow_key}/runs")
def run_workflow(extension_id: str, workflow_key: str, request: ExtensionWorkflowRun, db=Depends(get_db)):
    with _lock:
        extension = db.get(ExtensionDB, extension_id)
        if not extension:
            raise HTTPException(404, "Extension not found")
        if extension.status != "active":
            raise HTTPException(409, "Extension is not enabled")
        release = db.query(ExtensionReleaseDB).filter_by(extension_id=extension.id, version=extension.active_version).one()
        manifest = extension_manifest(release)
        workflow = next((item for item in manifest.workflows if item.id == workflow_key), None)
        if not workflow:
            raise HTTPException(404, "Extension workflow not found")
        granted = set(json.loads(extension.granted_permissions))
        required = {"workflows.write"}
        required.update({"tasks.write" if step.action == "create_task" else
                         "calendar.write" if step.action == "create_calendar_event" else
                         "reminders.write" if step.action == "create_reminder" else
                         "reminders.read" if step.action == "wait_for_reminder" else
                         "notifications.write" for step in workflow.plan.steps})
        if not required <= granted:
            raise HTTPException(403, "Extension no longer has all permissions required by this workflow")
        key = f"extension:{extension.id}:{extension.active_version}:{workflow_key}:{request.idempotency_key}" if request.idempotency_key else None
        result = create_workflow(db, workflow.plan, request.conversation_id, key)
        audit(db, extension.id, "workflow_run", extension.active_version, workflow=workflow_key, workflow_id=result.id)
        db.commit()
        return serialize_workflow(db, result)
