# `backend/tests/test_automations.py`

Focused tests for deterministic email automation behavior.

## Covered behavior

- A matching invoice rule creates one task, saves one attachment artifact, and applies a tag.
- Re-running the same rule for the same email returns `already_processed` and does not duplicate work.
- An unrelated email does not match a keyword condition.

The tests use an in-memory SQLite database and exercise `email_matches()` and `execute_email_rule()` directly.
