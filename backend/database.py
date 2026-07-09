from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, Boolean, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
    synced_at = Column(DateTime, default=datetime.utcnow)


def _migrate_sqlite():
    """Add columns introduced after a DB was first created (SQLite has no
    automatic schema migration). Safe to run on every startup."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if "emails" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("emails")}
    if "html_body" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE emails ADD COLUMN html_body TEXT DEFAULT ''"))


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()