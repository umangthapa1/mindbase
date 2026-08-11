# Backend

This directory contains the FastAPI backend application for Mindbase AI.

## Structure

- `main.py` - Entry point for the FastAPI application
- `database.py` - Database connection and initialization
- `models.py` - Pydantic models for request/response validation
- `ollama.py` - Ollama client integration
- `research.py` - Research functionality
- `memory.py` - Memory management
- `tasks_service.py` - Task scheduling and management
- `documents.py` - Document processing
- `imap_service.py` - Email IMAP service
- `automations.py` - Local email automation matching, actions, and run history
- `intelligence.py` - Intelligence processing
- `config.py` - Configuration settings
- `tests/` - Test files for backend components
- `requirements.txt` - Production dependencies
- `requirements-dev.txt` - Development dependencies

## Running the Backend

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn main:app
```

## Email Automation and Background Sync

When an IMAP account is connected, Mindbase can sync it automatically in the background without delaying application startup. A sync also runs immediately after an account is connected. Configure this behavior in `.env`:

```env
EMAIL_AUTO_SYNC=true
EMAIL_AUTO_SYNC_INTERVAL_SECONDS=300
EMAIL_AUTO_SYNC_MAX_RESULTS=20
```

Newly synced emails are evaluated against enabled automation rules. Supported actions save captured attachments, create follow-up tasks, tag emails, and record local notification events. Rule execution is idempotent per rule/email pair, preventing duplicate work during repeated syncs.

Attachments are stored locally in `uploads/email-attachments/` with generated filenames and owner-only file permissions. The IMAP importer limits each attachment to 25 MB and each email to 20 attachments.

Relevant API routes:

- `GET` / `POST` `/api/automations`
- `PUT` / `DELETE` `/api/automations/{rule_id}`
- `GET` `/api/automations/done`
- `GET` `/api/automations/attachments/{attachment_id}/download`
