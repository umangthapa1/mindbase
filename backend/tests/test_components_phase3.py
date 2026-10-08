"""Phase 3 declarative component and template regressions."""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import (Base, WorkspaceComponentDB, WorkspaceTemplateDB, WorkspaceTemplateVersionDB,
                      WorkflowDB, WorkflowStepDB)
from component_runtime import TemplateDefinition, seed_component_templates
from test_chat_tool_routing import chat_client


def definition(version="v1", *, actions=True):
    return {
        "schema_version": 1,
        "layout": "stack",
        "permissions": ["workflows.read", "workflows.write"] if actions else ["workflows.read"],
        "nodes": [
            {"id": "title", "type": "text", "label": version, "source": "title"},
            {"id": "status", "type": "status", "source": "status"},
            {"id": "progress", "type": "progress", "source": "progress"},
            {"id": "steps", "type": "list", "source": "steps"},
        ],
        "actions": ([{"id": "cancel", "label": "Cancel", "action": "cancel", "permission": "workflows.write"}]
                    if actions else []),
    }


def create_template(client, template_id="care-panel"):
    response = client.post("/api/workspace/templates", json={
        "id": template_id, "name": "Care panel", "description": "Test panel", "definition": definition(),
    })
    assert response.status_code == 200, response.text
    return response.json()


def component(client, template_id, **kwargs):
    response = client.post(f"/api/workspace/templates/{template_id}/instances", json=kwargs)
    assert response.status_code == 200, response.text
    component_id = response.json()["component"]
    rows = client.get("/api/workspace/components").json()
    return next(row for row in rows if row["id"] == component_id)


def test_builtin_template_is_seeded_and_workflow_instances_are_versioned(chat_client):
    client, db = chat_client
    templates = client.get("/api/workspace/templates").json()
    workflow = next(template for template in templates if template["id"] == "workflow-status")
    assert workflow["current_version"] == 1
    assert workflow["current"]["definition"]["nodes"][-1]["type"] == "list"
    response = client.post("/api/workspace/workflows", json={"plan": {
        "title": "Call grandpa", "steps": [{"id": "task", "action": "create_task", "inputs": {"title": "Call grandpa"}}]
    }})
    assert response.status_code == 200
    row = next(component for component in client.get("/api/workspace/components").json()
               if component["kind"] == "workflow")
    assert row["template"]["id"] == "workflow-status"
    assert row["template"]["version"] == 1
    assert row["props"]["progress"] == 1
    assert db.query(WorkspaceTemplateVersionDB).filter_by(template_id="workflow-status").count() == 1


def test_template_definition_is_strict_allowlisted_data(chat_client):
    client, db = chat_client
    invalid = definition()
    invalid["nodes"][0]["type"] = "html"
    invalid["nodes"][0]["html"] = "<script>alert(1)</script>"
    assert client.post("/api/workspace/templates", json={"id": "unsafe", "name": "Unsafe", "definition": invalid}).status_code == 422
    invalid = definition()
    invalid["permissions"] = ["shell.execute"]
    assert client.post("/api/workspace/templates", json={"id": "unsafe-perms", "name": "Unsafe", "definition": invalid}).status_code == 422
    invalid = definition()
    invalid["actions"][0]["permission"] = "tasks.write"
    assert client.post("/api/workspace/templates", json={"id": "wrong-perm", "name": "Wrong", "definition": invalid}).status_code == 422
    invalid = definition()
    invalid["extra_code"] = "eval('bad')"
    assert client.post("/api/workspace/templates", json={"id": "extra", "name": "Extra", "definition": invalid}).status_code == 422
    assert db.query(WorkspaceTemplateDB).filter(WorkspaceTemplateDB.id.in_(["unsafe", "unsafe-perms", "wrong-perm", "extra"])).count() == 0


def test_template_versions_are_immutable_and_instances_pin_their_version(chat_client):
    client, db = chat_client
    create_template(client)
    first = component(client, "care-panel", data={"title": "Old", "status": "active", "progress": 0, "steps": []})
    version = client.post("/api/workspace/templates/care-panel/versions", json={"definition": definition("v2", actions=False)})
    assert version.status_code == 200
    template = version.json()
    assert template["current_version"] == 2
    assert [row["version"] for row in template["versions"]] == [1, 2]
    old = next(row for row in client.get("/api/workspace/components").json() if row["id"] == first["id"])
    assert old["template"]["version"] == 1
    assert old["template"]["can_upgrade"] is True
    second = component(client, "care-panel", template_version=1, data={"title": "Pinned", "status": "active", "progress": 0, "steps": []})
    assert second["template"]["version"] == 1
    assert client.post(f"/api/workspace/components/{first['id']}/actions", json={"action": "upgrade"}).status_code == 200
    upgraded = next(row for row in client.get("/api/workspace/components").json() if row["id"] == first["id"])
    assert upgraded["template"]["version"] == 2
    assert next(row for row in client.get("/api/workspace/components").json() if row["id"] == second["id"])["template"]["version"] == 1
    assert db.query(WorkspaceTemplateVersionDB).filter_by(template_id="care-panel", version=1).one().definition != db.query(WorkspaceTemplateVersionDB).filter_by(template_id="care-panel", version=2).one().definition
    assert client.post("/api/workspace/templates/care-panel/versions", json={"definition": definition("v2", actions=False)}).status_code == 200
    assert client.get("/api/workspace/templates/care-panel").json()["current_version"] == 3


def test_component_data_is_text_only_and_lifecycle_is_persistent(chat_client):
    client, db = chat_client
    create_template(client)
    row = component(client, "care-panel", data={"title": "<img onerror=alert(1)>", "status": "active", "progress": 0.5, "steps": []})
    assert row["props"]["title"] == "<img onerror=alert(1)>"
    assert client.post(f"/api/workspace/components/{row['id']}/actions", json={"action": "archive"}).json()["lifecycle"] == "archived"
    archived = next(item for item in client.get("/api/workspace/components").json() if item["id"] == row["id"])
    assert archived["visible"] is False
    assert client.post(f"/api/workspace/components/{row['id']}/actions", json={"action": "restore"}).json()["visible"] is True
    assert db.get(WorkspaceComponentDB, row["id"]).lifecycle == "active"
    assert client.post(f"/api/workspace/components/{row['id']}/actions", json={"action": "upgrade"}).status_code == 200
    assert client.post(f"/api/workspace/components/{row['id']}/actions", json={"action": "execute"}).status_code == 422


def test_template_instances_require_existing_workflows_and_bound_data(chat_client):
    client, db = chat_client
    create_template(client)
    assert client.post("/api/workspace/templates/care-panel/instances", json={"workflow_id": "missing"}).status_code == 404
    too_large = {"title": "x" * 20_000}
    assert client.post("/api/workspace/templates/care-panel/instances", json={"data": too_large}).status_code == 422
    assert client.post("/api/workspace/templates/care-panel", json={"definition": definition()}).status_code == 405
    assert db.query(WorkspaceComponentDB).count() == 0


def test_template_archive_blocks_new_instances_but_keeps_old_version(chat_client):
    client, db = chat_client
    create_template(client)
    row = component(client, "care-panel", data={"title": "Pinned", "status": "active", "progress": 0, "steps": []})
    assert client.patch("/api/workspace/templates/care-panel", json={"status": "archived"}).status_code == 200
    assert client.post("/api/workspace/templates/care-panel/instances", json={}).status_code == 409
    old = next(item for item in client.get("/api/workspace/components").json() if item["id"] == row["id"])
    assert old["template"]["status"] == "archived"
    assert client.post("/api/workspace/templates/care-panel/versions", json={"definition": definition("new")}).status_code == 409
    assert client.patch("/api/workspace/templates/care-panel", json={"status": "active"}).status_code == 200
    assert client.post("/api/workspace/templates/care-panel/instances", json={}).status_code == 200


def test_template_definitions_survive_reopen_and_seed_is_idempotent(tmp_path):
    path = tmp_path / "components.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        seed_component_templates(db)
        seed_component_templates(db)
        assert db.query(WorkspaceTemplateDB).count() == 1
        assert db.query(WorkspaceTemplateVersionDB).count() == 1
    engine.dispose()
    engine = create_engine(f"sqlite:///{path}")
    with factory() as db:
        template = db.get(WorkspaceTemplateDB, "workflow-status")
        assert template.current_version == 1
        assert json.loads(db.query(WorkspaceTemplateVersionDB).one().definition)["schema_version"] == 1
    engine.dispose()
