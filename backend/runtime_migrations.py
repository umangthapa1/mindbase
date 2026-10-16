"""Upgrade the original workspace prototype without losing its rows or references.

SQLite cannot remove old NOT NULL constraints with ALTER COLUMN. Rebuild only
incompatible runtime tables, retain their extra metadata columns as nullable, and
copy IDs verbatim so existing foreign keys still refer to the same objects.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable


def _json(value, fallback):
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def _date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def _incompatible(table, columns):
    current = {column.name: column for column in table.columns}
    stored = {column["name"]: column for column in columns}
    if set(current) - set(stored):
        return True
    for name, column in stored.items():
        if name not in current:
            if not column["nullable"] and column.get("default") is None:
                return True
            continue
        expected = current[name]
        if column["type"]._type_affinity is not expected.type._type_affinity:
            return True
        if column["nullable"] != expected.nullable:
            return True
    return False


def _backup(connection):
    files = connection.exec_driver_sql("PRAGMA database_list").all()
    filename = next((row[2] for row in files if row[1] == "main"), "")
    connection.commit()
    if not filename:  # In-memory regression databases do not need a file backup.
        return
    path = Path(filename)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = path.with_name(f"{path.name}.pre-runtime-migration-{stamp}.bak")
    with sqlite3.connect(target) as backup:
        connection.connection.driver_connection.backup(backup)


def migrate_runtime_tables(engine, models):
    tables = {model.__tablename__: model.__table__ for model in models}
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    columns = {name: inspector.get_columns(name) for name in tables if name in existing}
    rebuild = [name for name, cols in columns.items() if _incompatible(tables[name], cols)]
    if not rebuild:
        return

    quote = engine.dialect.identifier_preparer.quote
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with engine.connect() as connection:
        _backup(connection)
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            # Explicit BEGIN makes SQLite DDL and all copied rows one transaction.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            rows = {name: [dict(row) for row in connection.exec_driver_sql(
                f"SELECT * FROM {quote(name)}").mappings()] for name in columns}
            components = {row["id"]: row for row in rows.get("workspace_components", [])}
            reminders = {row["id"]: row for row in rows.get("reminders", [])}
            events = {row["id"]: row for row in rows.get("workspace_events", [])}
            reminder_components = {row.get("component_id"): row for row in reminders.values() if row.get("component_id")}

            for name in rebuild:
                table = tables[name]
                temporary = f"__mindbase_migrate_{name}"
                ddl = str(CreateTable(table).compile(dialect=engine.dialect))
                ddl = ddl.replace(f"CREATE TABLE {quote(name)}", f"CREATE TABLE {quote(temporary)}", 1)
                connection.exec_driver_sql(ddl)
                extra = [col for col in columns[name] if col["name"] not in table.columns]
                for column in extra:
                    sql_type = column["type"].compile(dialect=engine.dialect)
                    connection.exec_driver_sql(
                        f"ALTER TABLE {quote(temporary)} ADD COLUMN {quote(column['name'])} {sql_type}")

                for position, original in enumerate(rows.get(name, [])):
                    row = dict(original)
                    if name == "capabilities":
                        manifest = _json(row.get("manifest"), {})
                        definition = _json(row.get("definition"), {})
                        if not definition:
                            definition = dict(manifest)
                            definition.setdefault("name", row.get("name") or row["id"])
                            definition.setdefault("permissions", [])
                        row.update(name=row.get("name") or definition["name"], definition=json.dumps(definition),
                                   enabled=bool(row.get("enabled", True)))
                    elif name == "workspace_components":
                        props = _json(row.get("props"), {})
                        props.setdefault("label", row.get("title") or "Workspace component")
                        kind = row.get("kind") or row.get("component_type") or "reminder"
                        if kind in {"timer", "timer_reminder", "countdown"}:
                            kind = "reminder"
                        if row["id"] in reminder_components:
                            kind = "reminder"
                        row.update(kind=kind, capability_id=row.get("capability_id") or
                                   ("workflows" if kind == "workflow" else "timer" if kind == "reminder" else "components"),
                                   props=json.dumps(props), position=position,
                                   visible=bool(row.get("visible", row.get("status") not in {"closed", "hidden", "archived"})),
                                   lifecycle=row.get("lifecycle") or "active", updated_at=row.get("updated_at") or row.get("created_at") or now)
                    elif name == "reminders":
                        component_id = row.get("component_id")
                        if component_id not in components:
                            component_id = str(uuid.uuid4())
                            generated = {"id": component_id, "kind": "reminder", "capability_id": "timer",
                                         "props": json.dumps({"label": row.get("label") or "Reminder"}), "position": len(components),
                                         "visible": True, "lifecycle": "active", "created_at": row.get("created_at") or now, "updated_at": now}
                            # Components have already been rebuilt (the caller specifies dependency order).
                            target = tables["workspace_components"]
                            names = list(generated)
                            connection.exec_driver_sql(
                                f"INSERT INTO {quote(target.name)} ({', '.join(quote(key) for key in names)}) "
                                f"VALUES ({', '.join('?' for _ in names)})", tuple(generated.values()))
                            components[component_id] = generated
                        component = components.get(component_id, {})
                        state = {**_json(component.get("props"), {}), **_json(component.get("state"), {})}
                        due = _date(row.get("due_at"))
                        remaining = row.get("remaining_seconds", state.get("remaining_seconds"))
                        if remaining is None:
                            remaining = max(0, (due - now).total_seconds()) if due else 0
                        status = row.get("status") or "active"
                        status = {"pending": "active", "running": "active", "triggered": "due", "fired": "due",
                                  "done": "completed", "canceled": "cancelled"}.get(status, status)
                        row.update(component_id=component_id, remaining_seconds=float(remaining), status=status,
                                   due_at=None if status == "paused" else row.get("due_at"),
                                   updated_at=row.get("updated_at") or now)
                    elif name == "workspace_events":
                        payload = _json(row.get("payload"), {})
                        row.update(type=row.get("type") or row.get("event_type") or "legacy.event",
                                   payload=json.dumps(payload), reminder_id=row.get("reminder_id") or
                                   (payload.get("reminder_id") if payload.get("reminder_id") in reminders else None))
                    elif name == "workspace_notifications":
                        linked_event = events.get(row.get("event_id"), {})
                        payload = _json(linked_event.get("payload"), {})
                        reminder_id = row.get("reminder_id") or payload.get("reminder_id")
                        # Legacy notifications can be unrelated to reminders.
                        row.update(reminder_id=reminder_id if reminder_id in reminders else None,
                                   acknowledged_at=row.get("acknowledged_at") or
                                   ((row.get("created_at") or now) if row.get("read") else None))

                    names = [column.name for column in table.columns if column.name in row]
                    names.extend(column["name"] for column in extra)
                    values = tuple(row.get(key) for key in names)
                    connection.exec_driver_sql(
                        f"INSERT INTO {quote(temporary)} ({', '.join(quote(key) for key in names)}) "
                        f"VALUES ({', '.join('?' for _ in names)})", values)

                connection.exec_driver_sql(f"DROP TABLE {quote(name)}")
                connection.exec_driver_sql(f"ALTER TABLE {quote(temporary)} RENAME TO {quote(name)}")
                for index in table.indexes:
                    from sqlalchemy.schema import CreateIndex
                    connection.exec_driver_sql(str(CreateIndex(index).compile(dialect=engine.dialect)))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql(f"PRAGMA foreign_keys={int(bool(foreign_keys))}")
            connection.commit()
