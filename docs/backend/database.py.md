# Mindbase Backend - database.py

## Overview
Database setup and management module using SQLAlchemy. Handles database initialization, table definitions, migration logic, and session management.

## Responsibilities
- Define SQLAlchemy models for all data entities
- Initialize database connection and create tables
- Handle schema migrations through idempotent ALTER TABLE statements
- Provide database session dependency for FastAPI routes
- Manage relationships between different entities

## Database Models

### Core Entities
- **ConversationDB**: Stores chat conversations with title and timestamps
- **MessageDB**: Individual messages within conversations (role, content, model)
- **NoteDB**: User notes with title, content, tags, and timestamps
- **TaskDB**: Tasks and to-do items with title, description, status, priority, due date, tags
- **CalendarEventDB**: Calendar events with title, description, start/end times, location, color
- **EmailDB**: Cached email messages from IMAP synchronization

### Model Fields
Each model includes standard fields like `id`, `created_at`, `updated_at` plus entity-specific fields:
- Conversations: `title`
- Messages: `role`, `content`, `model`
- Notes: `title`, `content`, `tags`
- Tasks: `title`, `description`, `status`, `priority`, `due_date`, `tags`
- Calendar Events: `title`, `description`, `start_at`, `end_at`, `all_day`, `location`, `color`
- Emails: `sender`, `subject`, `body`, `snippet`, `received_at`, `is_unread`, `message_id`

## Key Functions

### `init_db()`
- Creates all tables using SQLAlchemy's `create_all()`
- Runs migration functions to update schema
- Called during application startup

### `get_db()`
- FastAPI dependency that provides database sessions
- Ensures proper session cleanup after request

### `_migrate_sqlite()`
- Handles schema updates through idempotent ALTER TABLE statements
- Adds new columns to existing tables without data loss
- Example migration patterns:
  ```python
  if "column_name" not in existing_columns:
      exec(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
  ```

### Serialization Functions
- `serialize_task()`, `serialize_event()`, `serialize_email()`, etc.
- Convert database model instances to dictionaries for API responses
- Handle special formatting like date conversion and tag parsing

## Relationships
- Conversations have many Messages (one-to-many)
- Notes, Tasks, Calendar Events, and Emails are standalone entities
- All entities track creation and modification timestamps

## Usage in Application
- Imported in `main.py` for route handlers
- Used with FastAPI's `Depends(get_db)` for database sessions
- Services like `tasks_service.py` and `memory.py` interact directly with models
- Schema evolves through `_migrate_sqlite()` rather than external migration tools

## Storage Location
- Primary database: `data/workspace.db` (SQLite file)
- Directory created automatically if missing
- Included in `.gitignore` to prevent committing sensitive data