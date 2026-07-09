from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

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
