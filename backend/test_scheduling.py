import asyncio
import sys
import os
from datetime import datetime, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Base, TaskDB, CalendarEventDB
from backend.tasks_service import (
    task_manager,
    parse_natural_due,
    parse_task_payload,
    parse_event_timing,
    parse_time_range
)

def setup_db():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()

async def test_regex_date_parsing():
    print("Testing month name parsing...")
    # Reference date is set to a Sunday: 2026-06-07
    ref = datetime(2026, 6, 7, 12, 0, 0)
    
    # Test Month Day
    _, due1 = parse_natural_due("June 15th", reference=ref)
    assert due1 is not None
    assert due1.date() == date(2026, 6, 15)
    
    # Test Day Month
    _, due2 = parse_natural_due("15 of December", reference=ref)
    assert due2 is not None
    assert due2.date() == date(2026, 12, 15)
    
    # Test short month name
    _, due3 = parse_natural_due("Jan 10, 2027", reference=ref)
    assert due3 is not None
    assert due3.date() == date(2027, 1, 10)
    
    print("✓ Month name parsing tests passed!")

async def test_task_time_extraction():
    print("Testing task time extraction fixes...")
    # Test "Submit report on 12/25 at 4 PM"
    payload = parse_task_payload("Submit report on 12/25 at 4 PM")
    print("Payload parsed for 'Submit report on 12/25 at 4 PM':", payload)
    assert payload["title"] == "Submit report"
    assert payload["due_date"] is not None
    assert payload["due_date"].hour == 16
    assert payload["due_date"].minute == 0
    assert payload["due_date"].date() == date(datetime.now().year, 12, 25)
    
    # Test "Buy milk at 9:30 AM tomorrow"
    ref = datetime(2026, 6, 7, 12, 0, 0)
    # Note: parse_task_payload doesn't take reference explicitly but uses parse_natural_due which uses datetime.now()
    # We will just assert that time is extracted correctly.
    payload2 = parse_task_payload("Buy milk at 9:30 AM")
    assert payload2["title"] == "Buy milk"
    assert payload2["due_date"] is not None
    assert payload2["due_date"].hour == 9
    assert payload2["due_date"].minute == 30
    
    print("✓ Task time extraction tests passed!")

async def test_hybrid_parsing():
    print("Testing hybrid LLM-based parser...")
    db = setup_db()
    
    model = "qwen2.5:1.5b"
    # Create task via LLM
    res = await task_manager.process_user_message("add task call mom next Monday high priority", db, model=model)
    print("Create task result:", res)
    assert len(res) == 1
    assert res[0]["action"] == "create_task"
    assert res[0]["success"] is True
    
    # Check that task exists in DB
    task = db.query(TaskDB).filter(TaskDB.id == res[0]["item_id"]).first()
    assert task is not None
    assert task.title == "Call Mom"
    assert task.priority == "high"
    
    # Complete task via LLM
    res_comp = await task_manager.process_user_message("mark call mom as done", db, model=model)
    print("Complete task result:", res_comp)
    assert len(res_comp) == 1
    assert res_comp[0]["action"] == "complete_task"
    assert res_comp[0]["success"] is True
    
    # Check task completed status
    db.refresh(task)
    assert task.status == "completed"
    
    # Create event via LLM
    res_evt = await task_manager.process_user_message("put Monaco Grand Prix on my calendar for Sunday at 6:45pm to 7:45pm", db, model=model)
    print("Create event result:", res_evt)
    assert len(res_evt) == 1
    assert res_evt[0]["action"] == "create_event"
    assert res_evt[0]["success"] is True
    
    event = db.query(CalendarEventDB).filter(CalendarEventDB.id == res_evt[0]["item_id"]).first()
    assert event is not None
    assert event.title == "Monaco Grand Prix"
    
    print("✓ Hybrid parsing tests passed!")

async def main():
    try:
        await test_regex_date_parsing()
        await test_task_time_extraction()
        await test_hybrid_parsing()
        print("\n🎉 All scheduling verification tests passed successfully!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
