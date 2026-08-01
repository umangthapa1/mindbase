# Mindbase Backend - tasks_service.py

## Overview
Task and calendar management module that handles creation, modification, querying, and organization of tasks, to-do items, and calendar events. Includes natural language date parsing for intuitive scheduling.

## Responsibilities
- Manage SQLite database for tasks and calendar events
- Provide CRUD operations for tasks and events
- Handle task statuses, priorities, tags, and due dates
- Manage calendar events with start/end times, locations, and descriptions
- Parse natural language date/time expressions (e.g., "tomorrow at 3pm", "next Friday")
- Provide calendar view functionality for date ranges
- Handle task repetition and recurrence (basic support)
- Synchronize with memory system when appropriate
- Provide task suggestions based on context

## Key Classes & Methods

### TaskManager
Main class handling all task and calendar operations.

#### Task Operations
- `create_task(db, title, description, status, priority, due_date, tags)`: 
  Create new task with specified attributes
- `get_task(db, task_id)`: Retrieve specific task by ID
- `list_tasks(db)`: Get all tasks, ordered by due date
- `update_task(db, task_id, **kwargs)`: Modify task attributes
- `delete_db(db, task_id)`: Remove task from database
- `serialize_task(task)`: Convert task model to dictionary for API

#### Calendar Event Operations
- `create_event(db, title, start, end, description, all_day, location, color)`: 
  Create calendar event
- `get_event(db, event_id)`: Retrieve specific event
- `update_event(db, event_id, **kwargs)`: Modify event attributes
- `delete_event(db, event_id)`: Remove event
- `serialize_event(event)`: Convert event model to dictionary

#### Calendar Views
- `get_calendar_items(db, start_date, end_date, include_completed_tasks)`: 
  Get tasks and events within date range for calendar display
- Handles tasks with due dates and events with start/end times

#### Natural Language Parsing
- `_parse_date_string(date_string)`: 
  Main NLP date parsing function
  Handles: 
  - Relative dates: "tomorrow", "next week", "in 2 days"
  - Specific dates: "July 31, 2026", "2026-07-31"
  - Time specifications: "3pm", "15:00", "morning", "evening"
  - Combined: "tomorrow at 3pm", "next Friday morning"
  - Special: "today", "tonight", "next weekend"
  Returns datetime object or None if unparseable

#### Task Suggestions
- `suggest_task_from_text(text)`: 
  Extract potential task from natural language
  Identifies action items and commitments
  Returns suggested task title and due date hint

#### Utility Functions
- `_get_priority_label(priority)`: Convert numeric priority to label
- `_get_status_label(status)`: Convert status to human-readable label
- `_format_date_for_display(date)`: Format date for UI presentation
- `_is_overdue(task)`: Check if task is past due date

## Data Models

### Task Fields
- `id`: Unique identifier
- `title`: Short task description
- `description`: Detailed task information
- `status`: "pending", "in_progress", "completed", "cancelled"
- `priority`: 0 (low) to 4 (high) or None
- `due_date`: Optional datetime
- `tags`: Comma-separated string of tags
- `created_at`: Timestamp
- `updated_at`: Timestamp

### Calendar Event Fields
- `id`: Unique identifier
- `title`: Event title
- `description`: Event details
- `start_at`: Start datetime
- `end_at`: End datetime (nullable for all-day events)
- `all_day`: Boolean flag
- `location`: Event location string
- `color`: Hex color for display
- `created_at`: Timestamp
- `updated_at`: Timestamp

## Natural Language Date Parsing

### Supported Formats

#### Relative Dates
- "tomorrow", "yesterday"
- "today", "tonight"
- "this week", "next week", "last week"
- "this month", "next month"
- "in X days/weeks/months"
- "X days/weeks/months ago"

#### Specific Dates
- Month DD, YYYY formats: "July 31, 2026"
- ISO formats: "2026-07-31"
- DD/MM/YYYY or MM/DD/YYYY (locale dependent)
- YYYY-MM-DD HH:MM

#### Time Expressions
- "morning" (6am-9am), "afternoon" (12pm-5pm)
- "evening" (5pm-9pm), "night" (9pm-12am)
- Specific times: "3pm", "15:00", "09:30"
- "midnight" (00:00), "noon" (12:00)

#### Combined Expressions
- "tomorrow at 3pm"
- "next Friday morning"
- "July 31 in the evening"
- "in 2 weeks at 9am"

#### Special Cases
- "ASAP", "urgent" → treated as high priority, soon due date
- "when I have time" → no specific date
- Recurring hints: "every Monday", "daily", "weekly"

### Parsing Logic
1. Normalize input string (lowercase, trim)
2. Check for specific patterns in order of specificity
3. Extract date components and time components
4. Validate resulting datetime (no Feb 30, etc.)
5. Apply timezone (assumes local time)
6. Return datetime object or None

## Integration Points

### Called From
- `main.py`: In task and calendar endpoints (`/api/tasks/*`, `/api/calendar/*`)
- `intelligence.py`: For schedule context in chat responses
- Other services needing task/calendar functionality

### Dependencies
- `database.py`: For SQLAlchemy session and model access
- `models.py`: For Pydantic models in API endpoints
- `datetime`: Standard library for date handling
- `re`: Regular expressions for parsing

### Related Modules
- Works with `intelligence.py` to provide contextual schedule information
- Can synchronize important tasks to `memory.py` for long-term remembrance
- Used by `research.py` for tracking research actions

## Special Features

### Task Status Flow
- `pending` → `in_progress` → `completed`
- Can also go to `cancelled` from any state
- Completed tasks show in calendar view optionally
- Status affects display priority and styling

### Priority Levels
- 0: Low (light background)
- 1: Medium-low
- 2: Medium (default)
- 3: Medium-high
- 4: High (prominent display)
- None: No priority set

### Tagging System
- Comma-separated string stored in database
- Parsed to list for API responses
- Enables filtering and categorization
- Examples: "work", "personal", "errands", "admin"

### Date Handling
- All datetimes stored in UTC internally
- Converted to local time for display
- All-day events stored as date-only (time=00:00)
- Timezone considerations handled at presentation layer

### Recurring Tasks (Basic)
- Currently supports simple repetition through cloning
- Future enhancement: true recurrence rules (RRULE)
- Manual repetition: complete task creates next instance

## Usage Patterns

### Creating Tasks
```python
# Simple task
task = task_manager.create_task(
    db=session,
    title="Review project proposal",
    description="Look over the Q3 budget proposal",
    status="pending",
    priority=2,
    due_date=datetime(2026, 8, 1, 10, 0),
    tags=["work", "review"]
)

# From natural language (via intelligence layer)
# "Remind me to call mom tomorrow at 5pm"
# → Creates task with appropriate due date
```

### Calendar Views
```python
# Get this week's tasks and events
start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
end = start + timedelta(days=7)

items = task_manager.get_calendar_items(
    db=session,
    start=start,
    end=end,
    include_completed_tasks=False
)
# Returns mixed list of tasks and events for display
```

### Natural Language Examples
Input | Parsed Result
------|--------------
"tomorrow" | Tomorrow at 00:00
"next Monday" | Coming Monday at 00:00
"in 2 hours" | Current time + 2 hours
"July 31" | July 31 of current year at 00:00
"tomorrow at 3pm" | Tomorrow at 15:00
"Friday morning" | Coming Friday at 9:00 (default morning time)
"in a week" | Same time next week
"today at noon" | Today at 12:00

## Special Features

### Task Extraction from Chat
- Integrated with intelligence module to detect task intentions
- Phrases like "I need to...", "Remember to...", "Schedule..."
- Extracts action items and suggests task creation
- Requires user confirmation before creation

### Overdue Task Handling
- Automatic identification of past-due tasks
- Special styling in UI (typically red highlighting)
- Can be filtered or sorted by overdue status
- Recurring tasks: next instance calculated when completed

### View Filtering
- Tasks can be filtered by: status, priority, tags, date range
- Calendar view shows: tasks (as all-day on due date) + events
- Completed tasks optionally included in calendar views
- Search functionality across title and description

## Performance Considerations

### Database Operations
- Standard SQLAlchemy ORM operations
- Indexes on: due_date, status, created_at (in database.py)
- Typical queries: <10ms for reasonable dataset sizes
- List operations paginated implicitly through API limits

### Memory Usage
- Task objects lightweight
- Large numbers of tasks (>10k) may benefit from explicit pagination
- Calendar queries efficient due to date indexing

### Natural Language Parsing
- Regex-based, but not an issue
- Cached parsing results for repeated phrases (if implemented)
- Most delay comes from LLM interaction, not parsing

## Error Handling

### Validation Errors
- Invalid status/priority values: Clear error messages
- Malformed date strings: Returns None from parser
- Missing required fields: Pydantic validation catches early
- Database constraint violations: Handled gracefully

### Edge Cases
- Far future dates: Accepted but may trigger UI warnings
- Invalid times (25:00): Handled by parser limitations
- Timezone ambiguity: Assumes local time, documented
- Recurrence complexity: Currently limited to manual repetition

### Database Errors
- Connection failures: Logged and propagated as HTTP 500
- Constraint violations: Converted to appropriate 4xx errors
- Transaction rollbacks: Automatic on failure in async contexts

## Integration with AI Features

### Context Provision
- Provides schedule context to intelligence module for chat
- Includes: overdue tasks, today's items, upcoming deadlines
- Formats as natural language for LLM consumption
- Updated in real-time as tasks change

### Memory Synchronization
- Optional automatic creation of memories for completed tasks
- Important tasks can be flagged for long-term remembrance
- Task metadata (tags, priority) preserved in memory
- Helps build user productivity patterns over time

### Smart Suggestions
- Analyzes task patterns to suggest optimal times
- Learns from user completion habits
- Recommends breaking down large tasks
- Suggests delegation or batching opportunities

## Usage in Application

### API Endpoints
All task and calendar functionality exposed through:
- POST /api/tasks - Create task
- GET /api/tasks - List tasks
- GET /api/tasks/{id} - Get task
- PUT /api/tasks/{id} - Update task
- DELETE /api/tasks/{id} - Delete task
- POST /api/calendar/events - Create event
- GET /api/calendar - Get calendar items for range
- PUT /api/calendar/events/{id} - Update event
- DELETE /api/calendar/events/{id} - Delete event

### Frontend Consumption
- Used by tasks.html and calendar.html views
- Populates task lists, calendar views, and forms
- Enables drag-and-drop rescheduling (frontend implementation)
- Supports filtering, sorting, and search capabilities