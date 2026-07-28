"""Smoke tests for natural-language due-date parsing in tasks_service.py.

`parse_natural_due` is a pure function (no DB, no Ollama) and sits on the chat
scheduling hot path, so it's a cheap, high-value regression target. We pass an
explicit `reference` datetime so results are deterministic and not time-of-run
dependent.
"""
from datetime import datetime

from tasks_service import parse_natural_due


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
