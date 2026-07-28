from datetime import datetime
from typing import Annotated, Optional, List, Dict, Any
from pydantic import BaseModel, Field, BeforeValidator


def _coerce_tags(v):
    """Accept a list of tags or a comma-separated string; normalize to a list."""
    if v is None:
        return v
    if isinstance(v, str):
        return [t.strip() for t in v.split(",") if t.strip()]
    return v


# A tags field that accepts either ["a", "b"] or "a,b" from the client.
TagsField = Annotated[Optional[List[str]], BeforeValidator(_coerce_tags)]


class Message(BaseModel):
    id: Optional[str] = None
    conversation_id: str
    role: str
    content: str
    model: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ConversationCreate(BaseModel):
    title: Optional[str] = "New Conversation"

class ConversationUpdate(BaseModel):
    title: Optional[str] = None

class Conversation(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = 0

    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    model: Optional[str] = None
    agent_prompt: Optional[str] = None
    temperature: Optional[float] = None

class ChatResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    model: str
    created_at: datetime

class ModelInfo(BaseModel):
    name: str
    description: Optional[str] = None
    size: Optional[str] = None
    parameters: Optional[str] = None

class OllamaModel(BaseModel):
    name: str
    modified_at: str
    size: int
    digest: str


# ── Request models for the previously-untyped `data: dict` endpoints ──────────

class ModelSwitchRequest(BaseModel):
    model: str


class MemoryCreate(BaseModel):
    content: str
    type: str = "reference"
    tags: TagsField = None


class MemorySearch(BaseModel):
    query: str
    type: Optional[str] = None


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    tags: TagsField = None
    metadata: Optional[Dict[str, Any]] = None


class NoteCreate(BaseModel):
    title: str = "Untitled"
    content: str = ""
    tags: TagsField = None


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: TagsField = None


class TaskCreate(BaseModel):
    title: str
    due_date: Optional[str] = None
    description: str = ""
    status: str = "pending"
    priority: str = "medium"
    tags: TagsField = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    tags: TagsField = None
    due_date: Optional[str] = None


class CalendarEventCreate(BaseModel):
    title: str
    # Accept either short ("start"/"end") or explicit ("start_at"/"end_at") keys.
    start: Optional[str] = None
    start_at: Optional[str] = None
    end: Optional[str] = None
    end_at: Optional[str] = None
    description: str = ""
    all_day: bool = False
    location: str = ""
    color: str = "violet"


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    start: Optional[str] = None
    start_at: Optional[str] = None
    end: Optional[str] = None
    end_at: Optional[str] = None
    description: Optional[str] = None
    all_day: Optional[bool] = None
    location: Optional[str] = None
    color: Optional[str] = None


class ResearchRequest(BaseModel):
    query: str


class ResearchSaveRequest(BaseModel):
    report: Dict[str, Any]


class DocumentAsk(BaseModel):
    query: str


class EmailConnect(BaseModel):
    email: str
    app_password: str
    host: Optional[str] = None


class EmailSync(BaseModel):
    max_results: int = 20
    unread_only: bool = False
