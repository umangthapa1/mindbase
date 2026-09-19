"""Regression coverage for task actions initiated from chat."""
import asyncio
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, TaskDB
from database import CalendarEventDB
from tasks_service import task_manager


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_add_a_new_task_creates_a_record_without_model_help():
    db = _db()

    actions = asyncio.run(
        task_manager.process_user_message("add a new task to push to github.", db)
    )

    assert actions[0]["action"] == "create_task"
    assert actions[0]["success"] is True
    assert db.query(TaskDB).filter_by(id=actions[0]["item_id"]).one().status == "pending"


def test_mark_it_as_complete_commits_the_task_shown_in_previous_reply():
    db = _db()
    task = TaskDB(title="Push latest changes to GitHub", status="pending")
    db.add(task)
    db.commit()
    history = [{
        "role": "assistant",
        "content": "Pending tasks related to “quiz”:\n- **Push latest changes to GitHub** (pending) — no due date",
    }]

    actions = asyncio.run(
        task_manager.process_with_history("mark it as complete", history, db)
    )

    assert actions == [{
        "action": "complete_task",
        "success": True,
        "message": "Completed task: **Push latest changes to GitHub**",
        "item_id": task.id,
        "item_type": "task",
    }]
    db.refresh(task)
    assert task.status == "completed"


def test_delete_task_removes_the_record():
    db = _db()
    task = TaskDB(title="Temporary task", status="pending")
    db.add(task)
    db.commit()

    actions = asyncio.run(
        task_manager.process_user_message("delete the task Temporary task", db)
    )

    assert actions[0]["action"] == "delete_task"
    assert actions[0]["success"] is True
    assert db.query(TaskDB).filter_by(id=task.id).first() is None


def test_calendar_question_never_creates_an_event():
    db = _db()
    before = db.query(CalendarEventDB).count()

    actions = asyncio.run(
        task_manager.process_with_history("What events do I have on Monday?", [], db)
    )

    assert actions == []
    assert db.query(CalendarEventDB).count() == before


def test_calendar_range_for_a_named_weekday_is_one_day():
    start, end = task_manager.infer_date_range("What events do I have on Monday?")

    assert start.weekday() == 0
    assert (end - start).days == 1


def test_time_shift_preserves_existing_event_duration():
    db = _db()
    event = CalendarEventDB(
        title="Quiz",
        start_at=datetime(2026, 9, 21, 8, 0),
        end_at=datetime(2026, 9, 21, 13, 0),
    )
    db.add(event)
    db.commit()

    action = task_manager._reschedule_event_from_text(
        db, event, "change the time for Quiz from 8 am to 9 am"
    )

    assert action is not None
    db.refresh(event)
    assert event.start_at == datetime(2026, 9, 21, 9, 0)
    assert event.end_at == datetime(2026, 9, 21, 14, 0)
