# test_parse_natural_due.py

Tests for natural language date/time parsing functionality.

## Purpose

This test file verifies the accuracy and robustness of the natural language date/time parser used for scheduling tasks and setting reminders.

## Contents

- Tests for parsing relative dates (e.g., "tomorrow", "next week")
- Tests for parsing absolute dates (e.g., "July 31, 2026")
- Tests for parsing times (e.g., "2:30 PM", "14:30")
- Tests for parsing date ranges and recurrences
- Tests for handling ambiguous inputs
- Tests for timezone handling
- Tests for edge cases and invalid inputs

## Usage

Run with pytest:
```bash
pytest backend/tests/test_parse_natural_due.py
```

The parser is used in `tasks_service.py` for interpreting user input like "remind me to call mom tomorrow at 3pm".
