# Mindbase Backend - models.py

## Overview
Pydantic models for request validation, response serialization, and data transfer objects throughout the Mindbase API. Defines the schema for all API inputs and outputs ensuring data integrity and automatic documentation.

## Responsibilities
- Define request body schemas for POST/PUT endpoints
- Define response models for GET endpoints (often reusing request models)
- Provide data validation and automatic error messages
- Enable automatic OpenAPI/Swagger documentation generation
- Handle data conversion between JSON and Python objects
- Support complex nested structures and custom field types
- Provide examples for API documentation
- Handle special data types like lists of tags, timestamps, etc.

## Key Model Categories

### Request Models (Input Validation)
Used to validate incoming API request data.

#### Chat & Conversations
- `ConversationCreate`: 
  - `title`: str (optional) - Conversation title
- `ConversationUpdate`: 
  - `title`: str (optional) - New conversation title
- `ChatRequest`: 
  - `conversation_id`: str - Target conversation ID
  - `message`: str - User message content
  - `model`: str (optional) - Specific model to use
  - `temperature`: float (default 0.7) - Sampling temperature
  - `agent_prompt`: str (optional) - Custom agent instructions

#### Memory Management
- `MemoryCreate`: 
  - `content`: str - Memory content
  - `type`: str - Memory category (fact, preference, etc.)
  - `tags`: List[str] (optional) - Associated tags
- `MemoryUpdate`: 
  - `content`: str (optional) - Updated content
  - `tags`: List[str] (optional) - Updated tags
  - `metadata`: Dict (optional) - Additional metadata
- `MemorySearch`: 
  - `query`: str - Search query text
  - `type`: str (optional) - Filter by memory type
  - `limit`: int (default 10) - Maximum results

#### Notes
- `NoteCreate`: 
  - `title`: str - Note title
  - `content`: str - Note content
  - `tags`: List[str] (optional) - Associated tags
- `NoteUpdate`: 
  - `title`: str (optional) - Updated title
  - `content`: str (optional) - Updated content
  - `tags`: List[str] (optional) - Updated tags

#### Tasks
- `TaskCreate`: 
  - `title`: str - Task title
  - `description`: str (optional) - Task description
  - `status`: str (default "pending") - Task status
  - `priority`: int (optional, 0-4) - Priority level
  - `due_date`: str (optional) - ISO date string or natural language
  - `tags`: List[str] (optional) - Associated tags
- `TaskUpdate`: 
  - `title`: str (optional) - Updated title
  - `description`: str (optional) - Updated description
  - `status`: str (optional) - Updated status
  - `priority`: int (optional, 0-4) - Updated priority
  - `due_date`: str (optional) - Updated due date
  - `tags`: List[str] (optional) - Updated tags

#### Calendar Events
- `CalendarEventCreate`: 
  - `title`: str - Event title
  - `description`: str (optional) - Event description
  - `start`: str - Start datetime (ISO string)
  - `end`: str (optional) - End datetime (ISO string)
  - `all_day`: bool (default False) - All-day event flag
  - `location`: str (optional) - Event location
  - `color`: str (optional) - Hex color for display
- `CalendarEventUpdate`: 
  - `title`: str (optional) - Updated title
  - `description`: str (optional) - Updated description
  - `start`: str (optional) - Updated start datetime
  - `end`: str (optional) - Updated end datetime
  - `all_day`: bool (optional) - Updated all-day flag
  - `location`: str (optional) - Updated location
  - `color`: str (optional) - Updated color

#### Documents
- `DocumentAsk`: 
  - `query`: str - Question about document
- `ResearchSaveRequest`: 
  - `report`: Dict - Research report to save as note

#### Email (IMAP)
- `EmailConnect`: 
  - `email`: str - Email address/username
  - `app_password`: str - Application-specific password
  - `host`: str (optional) - IMAP server host
- `EmailSync`: 
  - `max_results`: int (optional) - Maximum emails to sync
  - `unread_only`: bool (optional) - Sync only unread messages

### Response Models (Output Serialization)
Used for outgoing API responses, often reusing request models with additional metadata.

#### Common Response Patterns
- List responses: `{"items": [...], "count": N}`
- Single item responses: Serialized model data
- Success responses: `{"status": "success", ...}` or HTTP 2xx
- Error responses: Handled by FastAPI automatically from exceptions

#### Specialized Responses
- `ChatResponse`: Used in streaming endpoint metadata
  - `intent`: str - Detected intent category
  - `context_sources`: List[str] - Sources of context used
  - `actions`: List[Dict] - Actions taken during processing
- Research progress updates: Various types as yielded by research agent

## Field Types & Validation

### String Fields
- Standard validation: min/max length, regex patterns
- Examples: 
  - `title`: max 200 chars
  - `content`: varies by context (notes can be long)
  - `email`: basic format validation
  - `hex_color`: regex for #RRGGBB format

### Numeric Fields
- Range validation where applicable
- Examples:
  - `priority`: 0-4 inclusive
  - `temperature`: 0.0-2.0 range
  - `limit`: positive integer with maximum
  - `max_results`: positive integer

### Date/Time Fields
- Accept ISO format strings
- Some fields accept natural language (parsed by service layer)
- Examples:
  - `due_date`: ISO string or "tomorrow at 3pm"
  - `start/end`: ISO datetime strings
  - Stored as datetime objects in database, serialized to ISO strings

### List Fields
- `tags`: List[str] with validation
- Automatic conversion from comma-separated strings
- Empty list allowed, None treated as empty
- Individual tag validation (length, characters)

### Boolean Fields
- Standard true/false values
- Examples: `all_day`, `unread_only`, `is_unread` in various models

### Complex Objects
- Nested models for related data
- Examples:
  - Research report contains multiple sections
  - Email models include sender/recipients as strings
  - Location data as simple strings

## Special Features

### Automatic Conversion
- Pydantic automatically converts:
  - JSON strings to appropriate Python types
  - Lists from JSON arrays
  - Nested objects to sub-models
  - Strings to datetime/date when appropriate
  - Comma-separated strings to lists for tags field

### Validation Errors
- Automatic 422 Unprocessable Entity responses for validation failures
- Detailed error messages indicating which fields failed
- Includes error type, location, and message for debugging
- Helpful for frontend form validation

### Examples in Documentation
- Each model can provide `schema_extra` with examples
- Appears in automatically generated Swagger/UI documentation
- Helps developers understand expected formats
- Examples based on real-world usage patterns

### Custom Validators
- Field-level validators for complex validation logic
- Root validators for cross-field validation
- Examples:
  - Ensure `end` date is after `start` date in calendar events
  - Validate priority is within allowed range
  - Check that email format is reasonable
  - Validate hex color format

### ORM Mode
- Configured to work with SQLAlchemy ORM objects
- `from_orm()` class method creates model from DB instance
- Enables direct serialization of database models
- Used in serialization functions like `serialize_task()`

## Usage Patterns

### In API Endpoints
```python
@app.post("/api/tasks")
def create_task(data: TaskCreate, db: Session = Depends(get_db)):
    # data is already validated TaskCreate instance
    # Access fields directly: data.title, data.description, etc.
    task = task_manager.create_task(db, data.title, data.description, ...)
    return serialize_task(task)
```

### Response Building
```python
def serialize_task(task: TaskDB) -> dict:
    # Convert SQLAlchemy model to Pydantic-compatible dict
    # Pydantic handles final validation and conversion
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "tags": task.tags.split(",") if task.tags else [],
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat()
    }
```

### Manual Validation
```python
# Validate data outside of endpoint context
try:
    chat_req = ChatRequest(
        conversation_id="conv_123",
        message="Hello world",
        temperature=0.8
    )
    # Use chat_req.model_dump() to get dict
except ValidationError as e:
    # Handle validation errors
    print(e.json())
```

## Model Relationships

### Inheritance & Composition
- Base models for common fields
- Specific models inherit or compose as needed
- Examples:
  - `TaskBase` with common task fields
  - `TaskCreate` and `TaskUpdate` inherit from base
  - Response models often reuse request model structure

### Generic Containers
- Dict[str, Any] for flexible metadata fields
- List[str] for homogenous lists like tags
- Union types for fields that can be multiple types

## Special Field Types

### TagsField
- Custom handling for tags that can be list or comma-separated string
- Automatically converts between formats
- Validation applied to individual tags
- Empty handling: None → [], "" → [], [""] → []

### DateTime Handling
- Input: Accept ISO strings, some accept natural language
- Internal: Stored as datetime objects
- Output: Serialized to ISO strings for JSON
- Timezone: Assumes UTC for storage, converts to local for display

### ID Fields
- String IDs for UUIDs and database IDs
- Primary keys in database, strings in API
- Validation: Non-empty string, format expectations

## Configuration & Customization

### Model Configuration
- `orm_mode = True` for SQLAlchemy compatibility
- `allow_population_by_field_name = True`
- `json_encoders` for special types (datetime, etc.)
- `validate_assignment = True` for runtime validation

### Field Configuration
- `alias` for different JSON vs Python field names
- `exclude` for fields not to serialize
- `default` and `default_factory` for default values
- `examples` for OpenAPI documentation

## Usage Across Application

### API Layer
- Primary use: Request/response validation in FastAPI endpoints
- Automatic documentation generation
- Error handling for malformed requests

### Service Layer
- Sometimes used for internal data transfer
- Less common as services often work directly with ORM models
- Used when crossing service boundaries or preparing API responses

### Data Flow
1. HTTP request → FastAPI parses JSON
2. Pydantic validates against request model
3. Validated data passed to endpoint function
4. Service functions work with data (often convert to/from ORM)
5. Response data validated against response model
6. Pydantic serializes to JSON for HTTP response

## Benefits

### Data Integrity
- Prevents malformed data from entering system
- Catches errors early at API boundary
- Ensures consistency across different endpoints

### Developer Experience
- Self-documenting through type hints and model definitions
- IDE autocompletion and type checking
- Clear contracts between frontend and backend

### Maintenance
- Centralized validation logic
- Easy to modify schemas in one place
- Automatic updates to API documentation
- Consistent error messages

### Integration
- Works seamlessly with FastAPI's dependency injection
- Compatible with SQLAlchemy ORM objects
- Supports complex nested data structures
- Enables evolution of API with backward compatibility considerations