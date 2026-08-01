# Mindbase Backend - intelligence.py

## Overview
Chat orchestration module that prepares context for AI conversations. Handles memory retrieval, document search, task/calendar context, email context, and prompt engineering for the LLM.

## Responsibilities
- Gather relevant context from multiple sources (memory, documents, tasks, calendar, email)
- Determine user intent from natural language input
- Construct optimized prompts for the LLM with appropriate context
- Handle special cases like email querying and task creation
- Prepare chat parameters including temperature and agent-specific prompts
- Return structured data for the main chat endpoint to use

## Key Functions

### `prepare_chat()`
Main entrypoint that orchestrates context gathering:
```python
async def prepare_chat(
    user_message: str,
    history: List[Dict],
    db: Session,
    model: str,
    agent_prompt: Optional[str] = None,
    temperature: float = 0.7,
    actions_taken: List[Dict] = [],
    conv: ConversationDB = None
) -> PreparedChatResult
```

Returns a `PreparedChatResult` containing:
- `messages`: Formatted message array for LLM (system, context, history, user)
- `intent`: Detected intent category (chat, task_creation, etc.)
- `context_sources`: List of context types included
- Other metadata for response formatting

### Context Gathering Functions
- `_get_memory_context()`: Retrieve relevant long-term memories
- `_get_document_context()`: Search uploaded documents for relevant content
- `_get_schedule_context()`: Get upcoming tasks and calendar events
- `_get_email_context()`: Retrieve emails when email intent detected
- `_get_agent_context()`: Add custom agent prompts if specified

### Intent Detection
- Natural language understanding to determine user goals
- Special handling for email queries (separate from general chat)
- Task creation triggers from phrases like "remind me to" or "schedule"
- Context-only queries that don't require LLM generation

### Prompt Engineering
- Constructs system messages with gathered context
- Orders context by relevance and importance
- Adds conversation history appropriately
- Formats user message with any special instructions

## Context Sources

### Memory Context
- Queries ChromaDB for semantically similar memories
- Filters by memory type if specified
- Returns top-k most relevant memories
- Includes memory creation time and relevance scoring

### Document Context
- Searches processed documents using vector similarity
- Returns relevant document chunks with source attribution
- Includes snippet and relevance score
- Used for document Q&A functionality

### Schedule Context
- Retrieves upcoming tasks (default: next 7 days)
- Gets calendar events for same time period
- Formats as natural language summary
- Includes overdue tasks and today's items

### Email Context
- Triggered when email intent detected in user message
- Searches local email cache using extracted filters
- Supports sender, subject, unread status, and time-based queries
- Can return full message body or just headers/previews
- Special handling for email follow-up questions

### Agent Context
- Custom prompts from frontend agent configuration
- Added as system messages when specified
- Enables specialized AI behaviors

## Integration Points

### Called From
- `main.py`: In the `/api/chat/messages` endpoint
- Receives user message, conversation history, and dependencies
- Returns prepared data for LLM interaction

### Dependencies
- `memory.py`: For long-term memory access
- `documents.py`: For document search and Q&A
- `tasks_service.py`: For task and calendar data
- `imap_service.py`: For email context when needed
- `database.py`: For session and model queries
- `ollama.py`: For model information (though not direct generation)

## Data Structures

### Internal Types
- Memory search results with metadata
- Document chunks with relevance scores
- Task/event summaries with timing information
- Email search results with filtering capabilities

### External Contracts
- Accepts Pydantic models from `models.py` for input validation
- Returns structured data compatible with streaming response format
- Works with SQLAlchemy Session for database queries

## Special Features

### Email Integration
- Sophisticated natural language email query parsing
- Context-aware follow-up question handling ("summarize the one from...")
- Options for full body retrieval vs header-only
- Unread filtering and time-based queries

### Context Optimization
- Deduplication of similar context items
- Relevance scoring and ranking
- Token limit awareness (though actual limiting done elsewhere)
- Context source tracking for response metadata

### Action Tracking
- Records what actions were taken during context gathering
- Used for response metadata and debugging
- Examples: "Retrieved 3 memories", "Found 2 relevant documents", "Created task: Buy groceries"

## Error Handling
- Graceful degradation when individual context sources fail
- Logging of errors without breaking chat flow
- Fallback to minimal context if services unavailable
- Specific handling for missing models or database issues

## Performance Considerations
- Async/await used for I/O-bound operations
- Database queries optimized with proper filtering
- Memory and document searches use vector similarity efficiently
- Context gathering runs in parallel where possible
- Results cached per conversation turn when appropriate