"""Phase 4 extension-pack boundaries; all tests use disposable isolated storage."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, ExtensionDB, ExtensionReleaseDB, ExtensionAuditDB, WorkspaceTemplateDB, WorkspaceTemplateVersionDB
from test_chat_tool_routing import chat_client


PERMISSIONS = ["workflows.read", "workflows.write", "tasks.write", "reminders.write", "reminders.read"]


def manifest(version="one", *, permissions=None, extra=None):
    result = {
        "schema_version": 1,
        "id": "care-pack",
        "name": f"Care pack {version}",
        "description": "A declarative local extension",
        "permissions": permissions or PERMISSIONS,
        "templates": [{
            "id": "care-panel", "name": f"Care panel {version}",
            "definition": {
                "schema_version": 1, "layout": "stack", "permissions": ["workflows.read"],
                "nodes": [{"id": "title", "type": "text", "source": "title"},
                          {"id": "status", "type": "status", "source": "status"}],
                "actions": [],
            },
        }],
        "workflows": [{
            "id": "stretch", "name": "Stretch reminder",
            "plan": {"title": "Stretch", "steps": [
                {"id": "reminder", "action": "create_reminder",
                 "inputs": {"label": "Stretch", "duration_seconds": 60}},
            ]},
        }],
    }
    if extra:
        result.update(extra)
    return result


def install(client, body=None):
    body = body or {"manifest": manifest(), "grant_permissions": PERMISSIONS}
    response = client.post("/api/workspace/extensions", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_extension_requires_explicit_permission_grants_before_mutation(chat_client):
    client, db = chat_client
    response = client.post("/api/workspace/extensions", json={"manifest": manifest(), "grant_permissions": []})
    assert response.status_code == 403
    assert db.query(ExtensionDB).count() == db.query(ExtensionReleaseDB).count() == 0
    response = client.post("/api/workspace/extensions", json={"manifest": manifest(),
        "grant_permissions": PERMISSIONS + ["shell.execute"]})
    assert response.status_code == 422
    assert db.query(ExtensionDB).count() == 0


def test_only_declarative_manifest_fields_are_accepted(chat_client):
    client, db = chat_client
    invalid = manifest(extra={"entrypoint": "python:run", "code": "os.remove('/')"})
    assert client.post("/api/workspace/extensions", json={"manifest": invalid, "grant_permissions": PERMISSIONS}).status_code == 422
    invalid = manifest(permissions=["workflows.read"])
    assert client.post("/api/workspace/extensions", json={"manifest": invalid, "grant_permissions": ["workflows.read"]}).status_code == 422
    assert db.query(ExtensionDB).count() == 0


def test_install_materializes_namespaced_template_and_runs_workflow_idempotently(chat_client):
    client, db = chat_client
    installed = install(client)
    assert installed["status"] == "active"
    assert installed["active_version"] == 1
    assert installed["templates"] == [{"id": "extension--care-pack--care-panel", "key": "care-panel", "name": "Care panel one"}]
    assert installed["workflows"] == [{"id": "stretch", "name": "Stretch reminder"}]
    assert len(installed["audit"]) == 1
    assert db.query(ExtensionReleaseDB).one().digest == installed["releases"][0]["digest"]
    instance = client.post("/api/workspace/templates/extension--care-pack--care-panel/instances", json={
        "data": {"title": "Grandpa", "status": "active"}})
    assert instance.status_code == 200, instance.text
    first = client.post("/api/workspace/extensions/care-pack/workflows/stretch/runs", json={"idempotency_key": "same-run"})
    assert first.status_code == 200, first.text
    second = client.post("/api/workspace/extensions/care-pack/workflows/stretch/runs", json={"idempotency_key": "same-run"})
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert db.query(ExtensionDB).count() == db.query(ExtensionReleaseDB).count() == 1
    assert db.query(WorkspaceTemplateDB).filter_by(source_extension_id="care-pack").count() == 1


def test_disable_archives_pack_templates_and_blocks_new_runs_without_stopping_old_instances(chat_client):
    client, db = chat_client
    install(client)
    instance = client.post("/api/workspace/templates/extension--care-pack--care-panel/instances", json={"data": {"title": "Old"}}).json()
    disabled = client.post("/api/workspace/extensions/care-pack/actions", json={"action": "disable"})
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert client.post("/api/workspace/extensions/care-pack/workflows/stretch/runs", json={}).status_code == 409
    assert client.post("/api/workspace/templates/extension--care-pack--care-panel/instances", json={}).status_code == 409
    component = next(row for row in client.get("/api/workspace/components").json() if row["id"] == instance["component"])
    assert component["template"]["status"] == "archived"
    enabled = client.post("/api/workspace/extensions/care-pack/actions", json={"action": "enable"})
    assert enabled.status_code == 200
    assert client.post("/api/workspace/extensions/care-pack/workflows/stretch/runs", json={"idempotency_key": "after-enable"}).status_code == 200


def test_release_update_pins_old_components_and_rollback_materializes_previous_definition(chat_client):
    client, db = chat_client
    install(client)
    old = client.post("/api/workspace/templates/extension--care-pack--care-panel/instances", json={"data": {"title": "Pinned"}}).json()
    release = client.post("/api/workspace/extensions/care-pack/versions", json={
        "manifest": manifest("two"), "grant_permissions": PERMISSIONS,
    })
    assert release.status_code == 200, release.text
    assert release.json()["active_version"] == 2
    new = client.post("/api/workspace/templates/extension--care-pack--care-panel/instances", json={"data": {"title": "New"}}).json()
    rows = client.get("/api/workspace/components").json()
    old_row = next(row for row in rows if row["id"] == old["component"])
    new_row = next(row for row in rows if row["id"] == new["component"])
    assert old_row["template"]["version"] == 1
    assert new_row["template"]["version"] == 2
    rollback = client.post("/api/workspace/extensions/care-pack/actions", json={"action": "rollback", "version": 1})
    assert rollback.status_code == 200
    assert rollback.json()["active_version"] == 1
    template = db.get(WorkspaceTemplateDB, "extension--care-pack--care-panel")
    assert template.current_version == 3  # New immutable template version, old instances remain pinned.
    assert json.loads(db.query(WorkspaceTemplateVersionDB).filter_by(template_id=template.id, version=3).one().definition)["nodes"][0]["source"] == "title"
    assert db.query(ExtensionAuditDB).filter_by(extension_id="care-pack").count() == 3


def test_releases_require_matching_ids_and_cannot_follow_uninstall(chat_client):
    client, db = chat_client
    install(client)
    changed = manifest("bad")
    changed["id"] = "different"
    assert client.post("/api/workspace/extensions/care-pack/versions", json={"manifest": changed,
        "grant_permissions": PERMISSIONS}).status_code == 422
    assert client.post("/api/workspace/extensions/care-pack/actions", json={"action": "uninstall"}).status_code == 200
    assert client.post("/api/workspace/extensions/care-pack/actions", json={"action": "enable"}).status_code == 409
    assert client.post("/api/workspace/extensions/care-pack/versions", json={"manifest": manifest("new"),
        "grant_permissions": PERMISSIONS}).status_code == 409
    assert db.get(ExtensionDB, "care-pack").status == "uninstalled"


def test_extension_audit_and_release_state_survive_reopen(tmp_path):
    path = tmp_path / "extensions.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    from extension_runtime import install_extension, ExtensionInstallRequest, action_extension, ExtensionAction
    with factory() as db:
        extension = install_extension(db, ExtensionInstallRequest(manifest=manifest(), grant_permissions=PERMISSIONS))
        action_extension(db, extension, ExtensionAction(action="disable"))
    engine.dispose()
    engine = create_engine(f"sqlite:///{path}")
    with sessionmaker(bind=engine)() as db:
        row = db.get(ExtensionDB, "care-pack")
        assert row.status == "disabled"
        assert db.query(ExtensionReleaseDB).count() == 1
        assert db.query(ExtensionAuditDB).count() == 2
    engine.dispose()
