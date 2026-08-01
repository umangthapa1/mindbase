# Mindbase Backend - main.py

## Overview
The main entrypoint for the FastAPI application. Contains all API route definitions, middleware configuration, application lifecycle management, and core request handling logic.

## Responsibilities
- Initialize and configure the FastAPI application
- Set up CORS middleware
- Define all API endpoints (chat, memory, notes, tasks, calendar, email, research, documents)
- Handle application lifespan events (startup/shutdown)
- Manage streaming chat responses with Server-Sent Events (SSE)
- Integrate with all backend services (Ollama, memory, tasks, email, etc.)

## Key Features
- **Streaming Chat Interface**: Uses SSE for real-time AI responses
- **Email Integration**: Full IMAP support with contextual email querying
- **Memory Management**: Long-term memory storage and retrieval
- **Task & Calendar**: Natural language scheduling and management
- **Document Processing**: Upload, process, and query local documents
- **Research Agent**: Offline multi-step research capabilities
- **Model Switching**: Dynamic AI model selection without restart

## API Endpoints

### Health & Configuration
- `GET /api/health` - Check application and Ollama connection status
- `GET /api/ollama/models` - List available Ollama models
- `POST /api/ollama/switch` - Switch to a different Ollama model

### Chat & Conversations
- `POST /api/chat/conversations` - Create new conversation
- `GET /api/chat/conversations` - List all conversations
- `GET /api/chat/conversations/{id}` - Get specific conversation
- `POST /api/chat/messages` - Send message and get AI response (SSE)
- `DELETE /api/chat/conversations/{id}` - Delete conversation
- `PUT /api/chat/conversations/{id}` - Update conversation title

### Memory Management
- `POST /api/memory/create` - Create new memory entry
- `GET /api/memory/list` - List all memories
- `GET /api/memory/list/{type}` - List memories by type
- `POST /api/memory/search` - Search memories by content
- `PUT /api/memory/{id}` - Update memory entry
- `DELETE /api/memory/{id}` - Delete memory entry

### Notes
- `POST /api/notes` - Create new note
- `GET /api/notes` - List all notes
- `GET /api/notes/{id}` - Get specific note
- `PUT /api/notes/{id}` - Update note
- `DELETE /api/notes/{id}` - Delete note

### Tasks
- `POST /api/tasks` - Create new task
- `GET /api/tasks` - List all tasks
- `GET /api/tasks/{id}` - Get specific task
- `PUT /api/tasks/{id}` - Update task
- `DELETE /api/tasks/{id}` - Delete task

### Calendar
- `GET /api/calendar` - Get calendar items for date range
- `POST /api/calendar/events` - Create calendar event
- `PUT /api/calendar/events/{id}` - Update calendar event
- `DELETE /api/calendar/events/{id}` - Delete calendar event

### Research
- `POST /api/research` - Start research process (SSE)
- `POST /api/research/save` - Save research report to notes

### Documents
- `POST /api/documents/upload` - Upload and process document
- `GET /api/documents` - List all documents
- `POST /api/documents/{id}/ask` - Ask questions about document
- `POST /api/documents/{id}/summary` - Generate document summary
- `DELETE /api/documents/{id}` - Delete document

### Email (IMAP)
- `GET /api/email/status` - Check email connection status
- `POST /api/email/connect` - Connect to email account
- `POST /api/email/disconnect` - Disconnect from email account
- `POST /api/email/sync` - Synchronize emails from server
- `GET /api/email/inbox` - List emails from local cache
- `GET /api/email/{id}` - Get specific email
- `POST /api/email/{id}/summarize` - Generate email summary

## Data Flow
1. HTTP requests arrive at route handlers in main.py
2. Handlers validate input using Pydantic models
3. Business logic delegated to appropriate service modules
4. Services interact with databases, Ollama, or external systems
5. Responses formatted and returned to client
6. For streaming endpoints, Server-Sent Events used for real-time updates

## Dependencies
- FastAPI: Web framework
- SQLAlchemy: ORM for database interactions
- Pydantic: Data validation and settings management
- Various backend service modules (ollama, memory, tasks_service, etc.)

## Initialization
The application uses FastAPI's lifespan event handler to:
1. Initialize database connection
2. Verify Ollama connectivity
3. Auto-pull required embedding model (nomic-embed-text) in background
4. Clean up resources on shutdown

## Error Handling
- HTTP exceptions raised for API errors with appropriate status codes
- Ollama connection errors handled gracefully
- Validation errors from Pydantic models automatically converted to 422 responses