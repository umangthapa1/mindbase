from sqlalchemy import create_engine, Column, String, DateTime, Integer, Float, Text, Boolean, ForeignKey, Table, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid
from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    # `check_same_thread=False` lets a pooled connection be checked out across the
    # worker threads we offload DB work onto (asyncio.to_thread in the async
    # routes). `timeout` is SQLite's busy-timeout (seconds): concurrent writers
    # *wait* for the file lock instead of erroring "database is locked" at once.
    connect_args={"check_same_thread": False, "timeout": 30},
    # Validate pooled connections before checkout (cheap "SELECT 1") and recycle
    # them hourly so a long-lived process never hands out a stale handle. A
    # modest pool headroom supports the parallelized chat-prepare gatherers.
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=10,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ConversationDB(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("MessageDB", back_populates="conversation", cascade="all, delete-orphan")

class MessageDB(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    model = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("ConversationDB", back_populates="messages")

class ModelInfoDB(Base):
    __tablename__ = "models_info"

    name = Column(String, primary_key=True)
    description = Column(String)
    size = Column(String)
    parameters = Column(String)

class NoteDB(Base):
    __tablename__ = "notes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    content = Column(Text, default="")
    tags = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TaskDB(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="pending")
    priority = Column(String, default="medium")
    due_date = Column(DateTime)
    tags = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CalendarEventDB(Base):
    __tablename__ = "calendar_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    all_day = Column(Integer, default=0)  # sqlite-friendly bool
    location = Column(String, default="")
    color = Column(String, default="violet")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailDB(Base):
    __tablename__ = "emails"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    gmail_id = Column(String, unique=True, index=True, nullable=False)
    thread_id = Column(String, nullable=True)
    subject = Column(String, default="")
    sender = Column(String, default="")
    snippet = Column(Text, default="")
    body = Column(Text, default="")            # clean plain text (LLM / snippet / fallback)
    html_body = Column(Text, default="")       # original HTML for rich rendering
    received_at = Column(DateTime, nullable=True)
    is_unread = Column(Boolean, default=True)
    processed = Column(Boolean, default=False)  # whether task/memory extraction has run
    tags = Column(String, default="")
    synced_at = Column(DateTime, default=datetime.utcnow)


class AutomationRuleDB(Base):
    __tablename__ = "automation_rules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    trigger = Column(String, nullable=False, default="email")
    condition = Column(Text, default="")
    actions = Column(Text, nullable=False, default="[]")  # JSON list
    details = Column(Text, default="")
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AutomationRunDB(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (UniqueConstraint("rule_id", "email_id", name="uq_automation_run_rule_email"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id = Column(String, ForeignKey("automation_rules.id"), nullable=False, index=True)
    email_id = Column(String, ForeignKey("emails.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="completed")
    result = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class EmailAttachmentDB(Base):
    __tablename__ = "email_attachments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email_id = Column(String, ForeignKey("emails.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    stored_name = Column(String, nullable=False, unique=True)
    content_type = Column(String, default="application/octet-stream")
    size = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AutomationArtifactDB(Base):
    __tablename__ = "automation_artifacts"
    __table_args__ = (UniqueConstraint("run_id", "attachment_id", name="uq_automation_artifact_run_attachment"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("automation_runs.id"), nullable=False, index=True)
    email_id = Column(String, ForeignKey("emails.id"), nullable=False, index=True)
    attachment_id = Column(String, ForeignKey("email_attachments.id"), nullable=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=True, index=True)
    kind = Column(String, nullable=False)  # attachment, task, tag, notification
    label = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class CapabilityDB(Base):
    __tablename__ = "capabilities"

    id = Column(String, primary_key=True)
    definition = Column(Text, nullable=False)  # Developer-owned JSON, never executable code
    enabled = Column(Boolean, nullable=False, default=True)


class WorkspaceTemplateDB(Base):
    __tablename__ = "workspace_templates"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    status = Column(String, nullable=False, default="active", index=True)
    current_version = Column(Integer, nullable=False, default=1)
    source_extension_id = Column(String, nullable=True, index=True)
    source_extension_version = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class WorkspaceTemplateVersionDB(Base):
    __tablename__ = "workspace_template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_workspace_template_version"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    template_id = Column(String, ForeignKey("workspace_templates.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    definition = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExtensionDB(Base):
    __tablename__ = "extensions"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    status = Column(String, nullable=False, default="active", index=True)
    active_version = Column(Integer, nullable=False, default=1)
    granted_permissions = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ExtensionReleaseDB(Base):
    __tablename__ = "extension_releases"
    __table_args__ = (UniqueConstraint("extension_id", "version", name="uq_extension_release_version"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    extension_id = Column(String, ForeignKey("extensions.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    manifest = Column(Text, nullable=False)
    digest = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExtensionAuditDB(Base):
    __tablename__ = "extension_audit"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    extension_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=True)
    action = Column(String, nullable=False)
    detail = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkspaceComponentDB(Base):
    __tablename__ = "workspace_components"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    capability_id = Column(String, ForeignKey("capabilities.id"), nullable=False)
    kind = Column(String, nullable=False)
    props = Column(Text, nullable=False, default="{}")
    template_id = Column(String, ForeignKey("workspace_templates.id"), nullable=True, index=True)
    template_version = Column(Integer, nullable=True)
    lifecycle = Column(String, nullable=False, default="active", index=True)
    position = Column(Integer, nullable=False, default=0)
    visible = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ReminderDB(Base):
    __tablename__ = "reminders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    component_id = Column(String, ForeignKey("workspace_components.id"), nullable=False, unique=True)
    conversation_id = Column(String, nullable=True, index=True)
    label = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active", index=True)
    due_at = Column(DateTime, nullable=True, index=True)  # UTC; null only while paused
    remaining_seconds = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class WorkflowDB(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    component_id = Column(String, ForeignKey("workspace_components.id"), nullable=False, unique=True)
    conversation_id = Column(String, nullable=True, index=True)
    idempotency_key = Column(String, nullable=True, unique=True)
    title = Column(String, nullable=False)
    plan = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="running", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class WorkflowStepDB(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (UniqueConstraint("workflow_id", "key", name="uq_workflow_step_key"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False, index=True)
    key = Column(String, nullable=False)
    position = Column(Integer, nullable=False)
    definition = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    result = Column(Text, nullable=False, default="{}")


class WorkflowLinkDB(Base):
    __tablename__ = "workflow_links"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False, index=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    reminder_id = Column(String, ForeignKey("reminders.id"), nullable=False, unique=True)


class WorkflowNotificationDB(Base):
    __tablename__ = "workflow_notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String, ForeignKey("workflows.id"), nullable=False, index=True)
    step_id = Column(String, ForeignKey("workflow_steps.id"), nullable=False, unique=True)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True, index=True)


class WorkspaceEventDB(Base):
    __tablename__ = "workspace_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String, nullable=False, index=True)
    reminder_id = Column(String, ForeignKey("reminders.id"), nullable=True)
    payload = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkspaceNotificationDB(Base):
    __tablename__ = "workspace_notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    reminder_id = Column(String, ForeignKey("reminders.id"), nullable=False, unique=True)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True)


def _migrate_sqlite():
    """Add columns/indexes introduced after a DB was first created (SQLite has no
    automatic schema migration). Safe to run on every startup — every statement
    is idempotent (a column-existence guard, or CREATE ... IF NOT EXISTS)."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    # ── Column additions ────────────────────────────────────────────────
    if "emails" in tables:
        existing = {col["name"] for col in inspector.get_columns("emails")}
        if "html_body" not in existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE emails ADD COLUMN html_body TEXT DEFAULT ''"))
        if "tags" not in existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE emails ADD COLUMN tags TEXT DEFAULT ''"))

    if "workspace_components" in tables:
        existing = {col["name"] for col in inspector.get_columns("workspace_components")}
        additions = {
            "template_id": "TEXT",
            "template_version": "INTEGER",
            "lifecycle": "TEXT NOT NULL DEFAULT 'active'",
            "updated_at": "DATETIME",
        }
        with engine.begin() as conn:
            for name, sql_type in additions.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE workspace_components ADD COLUMN {name} {sql_type}"))
            conn.execute(text("UPDATE workspace_components SET lifecycle = 'active' WHERE lifecycle IS NULL"))
            conn.execute(text("UPDATE workspace_components SET updated_at = created_at WHERE updated_at IS NULL"))

    if "workspace_templates" in tables:
        existing = {col["name"] for col in inspector.get_columns("workspace_templates")}
        additions = {"source_extension_id": "TEXT", "source_extension_version": "INTEGER"}
        with engine.begin() as conn:
            for name, sql_type in additions.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE workspace_templates ADD COLUMN {name} {sql_type}"))

    # ── Hot-path indexes ────────────────────────────────────────────────
    # These back the per-turn reads on the chat prepare path and the schedule
    # context builder: tasks by status/due date, events by start time/title,
    # messages by conversation, notes by recency. `create_all` has already made
    # every model table by this point, so the per-table guard is defensive only;
    # CREATE INDEX IF NOT EXISTS makes each statement re-runnable.
    indexes = [
        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status)"),
        ("tasks", "CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks (due_date)"),
        ("calendar_events", "CREATE INDEX IF NOT EXISTS idx_calendar_events_start_at ON calendar_events (start_at)"),
        ("calendar_events", "CREATE INDEX IF NOT EXISTS idx_calendar_events_title ON calendar_events (title)"),
        ("messages", "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages (conversation_id)"),
        ("notes", "CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes (updated_at)"),
        ("workspace_components", "CREATE INDEX IF NOT EXISTS idx_workspace_components_template ON workspace_components (template_id, template_version)"),
        ("workspace_template_versions", "CREATE INDEX IF NOT EXISTS idx_workspace_template_versions_template ON workspace_template_versions (template_id, version)"),
        ("extensions", "CREATE INDEX IF NOT EXISTS idx_extensions_status ON extensions (status)"),
        ("extension_releases", "CREATE INDEX IF NOT EXISTS idx_extension_releases_extension ON extension_releases (extension_id, version)"),
        ("extension_audit", "CREATE INDEX IF NOT EXISTS idx_extension_audit_extension ON extension_audit (extension_id, created_at)"),
    ]
    with engine.begin() as conn:
        for table, stmt in indexes:
            if table in tables:
                conn.execute(text(stmt))


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
