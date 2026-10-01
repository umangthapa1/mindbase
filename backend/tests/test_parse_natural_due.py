"""Smoke tests for natural-language due-date parsing in tasks_service.py.

`parse_natural_due` is a pure function (no DB, no Ollama) and sits on the chat
scheduling hot path, so it's a cheap, high-value regression target. We pass an
explicit `reference` datetime so results are deterministic and not time-of-run
dependent.
"""
from datetime import datetime, timedelta

import pytest

from intent_routing import route_message
from tasks_service import parse_natural_due, parse_task_payload, parse_event_timing


def test_tomorrow_sets_end_of_day():
    ref = datetime(2026, 7, 27, 12, 0, 0)
    cleaned, due = parse_natural_due("buy milk tomorrow", reference=ref)
    assert cleaned == "buy milk"
    assert due == datetime(2026, 7, 28, 23, 59, 59)


def test_today_sets_end_of_today():
    ref = datetime(2026, 7, 27, 9, 30)
    cleaned, due = parse_natural_due("call mom today", reference=ref)
    assert cleaned == "call mom"
    assert due == datetime(2026, 7, 27, 23, 59, 59)


def test_in_n_days():
    ref = datetime(2026, 7, 27)
    cleaned, due = parse_natural_due("submit report in 3 days", reference=ref)
    assert cleaned == "submit report"
    assert due == datetime(2026, 7, 30, 23, 59, 59)


def test_no_date_returns_none_due_and_untouched_text():
    cleaned, due = parse_natural_due("just a regular task with no date")
    assert due is None
    assert cleaned == "just a regular task with no date"


def test_time_of_day_keeps_resolved_date():
    # "tomorrow" sets the date; "evening" overrides the time to 18:00 but must
    # keep tomorrow's date rather than snapping back to today.
    ref = datetime(2026, 7, 27, 12, 0, 0)
    cleaned, due = parse_natural_due("dentist tomorrow evening", reference=ref)
    assert cleaned == "dentist"
    assert due == datetime(2026, 7, 28, 18, 0, 0)


@pytest.mark.parametrize("phrase,minutes", [
    ("in 15 minutes", 15),
    ("in like 15 mins", 15),
    ("in about 15 min", 15),
    ("in 15m", 15),
    ("in an hour", 60),
    ("in 2 hrs", 120),
    ("in 1.5 hours", 90),
    ("in 1 hour and 30 minutes", 90),
])
def test_relative_minutes_and_hours_keep_the_exact_time(phrase, minutes):
    ref = datetime(2026, 10, 1, 9, 34, 42)
    cleaned, due = parse_natural_due(f"push code {phrase}", reference=ref)
    assert cleaned == "push code"
    assert due == ref + timedelta(minutes=minutes)


def test_relative_reminder_rolls_over_midnight_and_year():
    ref = datetime(2026, 12, 31, 23, 55)
    _, due = parse_natural_due("push code in 15 mins", reference=ref)
    assert due == datetime(2027, 1, 1, 0, 10)


@pytest.mark.parametrize("phrase", ["in -15 mins", "in 0 minutes"])
def test_invalid_relative_reminder_does_not_become_an_undated_task(phrase):
    with pytest.raises(ValueError):
        parse_natural_due(f"push code {phrase}")


def test_reported_reminder_has_a_clean_title_and_timed_due_date():
    message = "i need to push my projects code to my github can u remind me to do it in like 15 mins"
    route = route_message(message)
    ref = datetime(2026, 10, 1, 9, 34, 42)
    payload = parse_task_payload(route.task_text, reference=ref)
    assert payload["title"] == "Push my projects code to my github"
    assert payload["due_date"] == datetime(2026, 10, 1, 9, 49, 42)
    assert "remind" not in payload["description"]
    assert "mins" not in payload["description"]


def test_relative_calendar_timing_does_not_fall_back_to_ten_am():
    ref = datetime(2026, 10, 1, 14, 30)
    title, start, end = parse_event_timing("Team meeting in 15 mins", reference=ref)
    assert title == "Team meeting"
    assert start == ref + timedelta(minutes=15)
    assert end == start + timedelta(hours=1)


def test_relative_time_wins_over_a_time_word_in_the_task_title():
    ref = datetime(2026, 10, 1, 14, 30)
    payload = parse_task_payload("review evening report in about 15 minutes", reference=ref)
    assert payload["title"] == "Review evening report"
    assert payload["due_date"] == ref + timedelta(minutes=15)
    assert payload["description"] == "Track and complete: Review evening report."
