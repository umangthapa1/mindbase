"""Regression coverage for upgrading databases created before Phase 1."""
import json

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import database
from capabilities import CORE_CAPABILITIES, seed_capabilities


def test_legacy_capabilities_table_gets_runtime_columns_and_definitions(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE capabilities (id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, enabled BOOLEAN DEFAULT 0)"))
        connection.execute(text("INSERT INTO capabilities (id, name, category, enabled) VALUES ('tasks', 'Tasks', 'planning', 0)"))

    monkeypatch.setattr(database, "engine", engine)
    database._migrate_sqlite()
    columns = {column["name"] for column in inspect(engine).get_columns("capabilities")}
    assert {"id", "name", "definition", "enabled"} <= columns

    with sessionmaker(bind=engine)() as db:
        seed_capabilities(db)
        tasks = db.get(database.CapabilityDB, "tasks")
        assert json.loads(tasks.definition) == CORE_CAPABILITIES["tasks"]
        assert tasks.enabled is False
        assert db.query(database.CapabilityDB).count() == len(CORE_CAPABILITIES)
    engine.dispose()


def test_original_runtime_schema_migrates_before_app_seed_and_preserves_ids(tmp_path, monkeypatch):
    path = tmp_path / "original-runtime.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE capabilities (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
                category TEXT NOT NULL, manifest TEXT NOT NULL, version TEXT NOT NULL,
                enabled BOOLEAN NOT NULL, created_at DATETIME, updated_at DATETIME,
                UNIQUE(name)
            )
        """))
        connection.execute(text("""
            CREATE TABLE workspace_components (
                id TEXT PRIMARY KEY, component_type TEXT NOT NULL, title TEXT NOT NULL,
                props TEXT NOT NULL, state TEXT NOT NULL, status TEXT NOT NULL,
                position TEXT NOT NULL, created_at DATETIME, updated_at DATETIME
            )
        """))
        connection.execute(text("""
            CREATE TABLE reminders (
                id TEXT PRIMARY KEY, label TEXT NOT NULL, due_at DATETIME NOT NULL,
                status TEXT NOT NULL, notification_text TEXT NOT NULL, component_id TEXT,
                task_id TEXT, created_at DATETIME, updated_at DATETIME, completed_at DATETIME
            )
        """))
        connection.execute(text("""
            CREATE TABLE workspace_events (
                id TEXT PRIMARY KEY, event_type TEXT NOT NULL, payload TEXT NOT NULL,
                source TEXT NOT NULL, created_at DATETIME, processed_at DATETIME
            )
        """))
        connection.execute(text("""
            CREATE TABLE workspace_notifications (
                id TEXT PRIMARY KEY, event_id TEXT, kind TEXT NOT NULL, title TEXT NOT NULL,
                message TEXT NOT NULL, read BOOLEAN NOT NULL, created_at DATETIME
            )
        """))
        connection.execute(text("INSERT INTO capabilities VALUES (:id,:name,:description,:category,:manifest,:version,:enabled,NULL,NULL)"),
                           {"id": "tasks", "name": "Tasks", "description": "Tasks", "category": "planning", "manifest": "{}", "version": "1", "enabled": 0})
        connection.execute(text("INSERT INTO workspace_components VALUES (:id,:type,:title,:props,:state,:status,:position,NULL,NULL)"),
                           {"id": "component-1", "type": "countdown", "title": "Drink water", "props": json.dumps({"label": "Drink water"}),
                            "state": json.dumps({"remaining_seconds": 10}), "status": "active", "position": "0"})
        connection.execute(text("INSERT INTO reminders VALUES ('reminder-1','Drink water','2026-10-08 09:05:00','pending','Drink water','component-1',NULL,NULL,NULL,NULL)"))
        connection.execute(text("INSERT INTO workspace_events VALUES (:id,:type,:payload,'legacy',NULL,NULL)"),
                           {"id": "event-1", "type": "reminder.due", "payload": json.dumps({"reminder_id": "reminder-1"})})
        connection.execute(text("INSERT INTO workspace_notifications VALUES ('notification-1','event-1','info','Reminder','Drink water',0,NULL)"))

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    database.init_db()

    with database.SessionLocal() as db:
        seed_capabilities(db)
        assert db.get(database.CapabilityDB, "tasks").enabled is False
        assert db.get(database.ReminderDB, "reminder-1").component_id == "component-1"
        assert db.get(database.WorkspaceComponentDB, "component-1").kind == "reminder"
        assert db.get(database.WorkspaceEventDB, "event-1").reminder_id == "reminder-1"
        assert db.get(database.WorkspaceNotificationDB, "notification-1").reminder_id == "reminder-1"
        assert db.get(database.WorkspaceNotificationDB, "notification-1").acknowledged_at is None
    engine.dispose()


def test_fastapi_lifespan_starts_against_original_schema(tmp_path, monkeypatch):
    # Reuse the same old-table fixture through the migration test setup without
    # opening the user's database. This exercises the actual app lifespan path.
    path = tmp_path / "startup.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE capabilities (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, category TEXT NOT NULL, manifest TEXT NOT NULL, version TEXT NOT NULL, enabled BOOLEAN NOT NULL, created_at DATETIME, updated_at DATETIME, UNIQUE(name))"))
        connection.execute(text("INSERT INTO capabilities VALUES ('tasks','Tasks','Tasks','planning','{}','1',0,NULL,NULL)"))
        connection.execute(text("CREATE TABLE workspace_components (id TEXT PRIMARY KEY, component_type TEXT NOT NULL, title TEXT NOT NULL, props TEXT NOT NULL, state TEXT NOT NULL, status TEXT NOT NULL, position TEXT NOT NULL, created_at DATETIME, updated_at DATETIME)"))
        connection.execute(text("CREATE TABLE reminders (id TEXT PRIMARY KEY, label TEXT NOT NULL, due_at DATETIME NOT NULL, status TEXT NOT NULL, notification_text TEXT NOT NULL, component_id TEXT, task_id TEXT, created_at DATETIME, updated_at DATETIME, completed_at DATETIME)"))
        connection.execute(text("CREATE TABLE workspace_events (id TEXT PRIMARY KEY, event_type TEXT NOT NULL, payload TEXT NOT NULL, source TEXT NOT NULL, created_at DATETIME, processed_at DATETIME)"))
        connection.execute(text("CREATE TABLE workspace_notifications (id TEXT PRIMARY KEY, event_id TEXT, kind TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL, read BOOLEAN NOT NULL, created_at DATETIME)"))

    import main
    from starlette.testclient import TestClient

    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(main, "EMAIL_AUTO_SYNC", False)

    async def offline(*args, **kwargs):
        return False

    monkeypatch.setattr(main.ollama_client, "check_health", offline)
    with TestClient(main.app) as client:
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        assert len(response.json()) == len(CORE_CAPABILITIES)
    engine.dispose()
