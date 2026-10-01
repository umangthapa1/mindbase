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

## Chat routing

`intent_routing.py` owns tool selection before any model call or action. `main.py`
executes the decision using the existing task manager and local inbox query:

- **add_task:** Create a to-do/reminder for a requested future action; **do not use** for questions about existing mail or inbox contents.
- **check_mail:** Look up existing emails, messages, or replies; **do not use** when the user wants a task reminding them to handle mail.
- **complete_task:** Complete the single task just discussed; **do not use** for negations, future plans, or ambiguous references.

| Request | Route |
| --- | --- |
| “Remind me to check my email tomorrow” | add_task |
| “Add reply to Alice's email to my tasks” | add_task |
| “I need to email Alice” | add_task |
| “Any new mail?” | check_mail |
| “Did Alice reply?” | check_mail, filtered to Alice |
| “Email Alice” | Ask: “Do you want me to add a task or check your email?” |

Explicit task requests take precedence over email words in their content, even
following an inbox search. Answering the clarification with “add a task” or
“check mail” resumes the original request; “yes” alone does not choose a tool.
Factual memory requests remain chat/memory requests; task/mail commands do not
also extract an unrequested memory. Explicit calendar events and existing
task/calendar updates retain their existing scheduling handler.

Relative task reminders accept minutes/hours (for example, “in like 15 mins”,
“in an hour”, or “in 1 hour and 30 minutes”) and preserve the exact relative due
time. Embedded wording such as “can u remind me to do it” is removed from the
title, and timed confirmations show the local date and clock time.

“Yep done” and grounded statements such as “I pushed the code” complete the
single task just discussed without a model call. Repeating completion confirms
that it is already completed; multiple matches, deleted references, or a different
activity ask which task instead of updating an arbitrary one. A negation or future
plan is not a completion command.

**Reminder limitation:** a reminder is a task with a due time. There is currently
no scheduled desktop/browser notification delivery service, so saving it does not
promise a pop-up when it becomes due.

Task creation, contextual completion, inbox listings, and clarification need no model inference.
Summaries, drafts, complex scheduling, and general chat retain the selected model
and streaming behavior. Local-only conversations get a short title from the
request instead of invoking a model just for a title. Mail lookup reads locally
synced messages; it does not send email or force a remote mailbox refresh.

Reproduce the server-side routing benchmark (synthetic data, real local Ollama):

```bash
python backend/benchmarks/benchmark_chat_routing.py --samples 3 --timeout 75
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
