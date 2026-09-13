# `backend/automations.py`

Local, deterministic email automation execution.

## Responsibilities

- Match enabled email rules against subject, sender, body, and snippet text.
- Execute supported actions exactly once per rule/email pair.
- Record automation runs and generated artifacts for the Done view.
- Serialize rules and run history for the API layer.

## Supported actions

The `actions` JSON field accepts:

- `save` - saves linked email attachments as automation artifacts.
- `task` - creates a follow-up task containing the email context.
- `tag` - adds a tag parsed from the rule details, defaulting to `automated`.
- `notify` - records a local notification artifact. It does not send a desktop or push notification.

## Matching

`email_matches()` only handles enabled `email` rules. An empty condition matches every email. Otherwise, the condition matches when it appears in the email text, or when all non-stop-word tokens are present.

## Idempotency

`execute_email_rule()` checks `AutomationRunDB` before doing work. A repeated sync returns `already_processed` and does not create duplicate tasks, tags, or saved artifacts.

## Integration

`process_new_emails()` loads enabled email rules and evaluates each newly synced message. The API serialization helpers are used by the automation routes in `backend/main.py`.
