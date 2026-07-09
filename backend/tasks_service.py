"""
Tasks, calendar, and chat-driven scheduling actions.
"""
from __future__ import annotations

import re
import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from database import CalendarEventDB, TaskDB
from ollama import ollama_client

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
VALID_STATUSES = {"pending", "in_progress", "completed"}
VALID_PRIORITIES = {"high", "medium", "low"}

AUTO_TAG_KEYWORDS = {
    "work": ("work", "office", "client", "meeting", "project", "deadline", "report"),
    "school": ("homework", "exam", "class", "study", "assignment", "essay"),
    "health": ("doctor", "gym", "workout", "dentist", "medicine"),
    "home": ("groceries", "clean", "laundry", "repair", "chores"),
    "finance": ("bill", "pay", "tax", "budget", "invoice"),
}

TIME_OF_DAY = {
    "morning": 9,
    "afternoon": 14,
    "evening": 18,
    "night": 20,
}
@dataclass
class ActionResult:
    action: str
    success: bool
    message: str
    item_id: Optional[str] = None
    item_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "success": self.success,
            "message": self.message,
            "item_id": self.item_id,
            "item_type": self.item_type,
        }


def normalize_calendar_text(text: str) -> str:
    """Fix common typos so calendar commands match."""
    return re.sub(r"\bcalender\b", "calendar", text, flags=re.I)


def _parse_clock(
    hour_s: str,
    minute_s: Optional[str],
    ampm: Optional[str],
    base_date: date,
) -> datetime:
    hour = int(hour_s)
    minute = int(minute_s) if minute_s else 0
    ampm = (ampm or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif not ampm and hour <= 7 and minute_s:
        hour += 12
    return datetime.combine(base_date, datetime.min.time()).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def parse_time_range(text: str, base_date: Optional[date] = None) -> Optional[Tuple[datetime, datetime]]:
    """e.g. '6 45 pm to 7 45 pm' or '6:45pm - 7:45pm'."""
    base = base_date or datetime.now().date()
    m = re.search(
        r"(\d{1,2})\s*(?::|\s+)?(\d{2})?\s*(am|pm)?\s*(?:to|until|-)\s*"
        r"(\d{1,2})\s*(?::|\s+)?(\d{2})?\s*(am|pm)?",
        text,
        re.I,
    )
    if not m:
        return None
    ampm_start = m.group(3) or m.group(6)
    ampm_end   = m.group(6) or m.group(3)
    start = _parse_clock(m.group(1), m.group(2), ampm_start, base)
    end = _parse_clock(m.group(4), m.group(5), ampm_end, base)
    if end <= start:
        end += timedelta(hours=12)
    return start, end


def _parse_date_string(value: str) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:len(fmt)], fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None


def parse_natural_due(text: str, reference: Optional[datetime] = None) -> Tuple[str, Optional[datetime]]:
    """Strip due-date phrases from text; return cleaned text and due datetime (end of day)."""
    ref = reference or datetime.now()
    lower = text.lower()
    due: Optional[datetime] = None
    cleaned = text

    weekday_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }

    def end_of_day(d: date) -> datetime:
        return datetime.combine(d, datetime.max.time().replace(microsecond=0))

    if re.search(r"\btoday\b", lower):
        due = end_of_day(ref.date())
        cleaned = re.sub(r"\b(today|by today|due today)\b", "", cleaned, flags=re.I)
    elif re.search(r"\btomorrow\b", lower):
        due = end_of_day(ref.date() + timedelta(days=1))
        cleaned = re.sub(r"\b(tomorrow|by tomorrow|due tomorrow)\b", "", cleaned, flags=re.I)
    elif m := re.search(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower):
        target = weekday_map[m.group(1)]
        days = (target - ref.weekday() + 7) % 7
        if days == 0:
            days = 7
        due = end_of_day(ref.date() + timedelta(days=days))
        cleaned = re.sub(m.group(0), "", cleaned, flags=re.I)
    elif m := re.search(
        r"\b(?:on|by|due|for\s+)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,\s*(\d{2,4})|\s+(\d{2,4}))?\b",
        lower,
        re.I
    ):
        months_map = {
            "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
            "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
            "august": 8, "aug": 8, "september": 9, "sep": 9, "october": 10, "oct": 10,
            "november": 11, "nov": 11, "december": 12, "dec": 12
        }
        month = months_map[m.group(1).lower()]
        day = int(m.group(2))
        year_val = m.group(3) or m.group(4)
        year = int(year_val) if year_val else ref.year
        if year < 100:
            year += 2000
        try:
            due = end_of_day(date(year, month, day))
            cleaned = re.sub(m.group(0), "", cleaned, flags=re.I)
        except ValueError:
            pass
    elif m := re.search(
        r"\b(?:on|by|due|for\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[a-z]*(?:\s*,\s*(\d{2,4})|\s+(\d{2,4}))?\b",
        lower,
        re.I
    ):
        months_map = {
            "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
            "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
            "august": 8, "aug": 8, "september": 9, "sep": 9, "october": 10, "oct": 10,
            "november": 11, "nov": 11, "december": 12, "dec": 12
        }
        day = int(m.group(1))
        month = months_map[m.group(2).lower()]
        year_val = m.group(3) or m.group(4)
        year = int(year_val) if year_val else ref.year
        if year < 100:
            year += 2000
        try:
            due = end_of_day(date(year, month, day))
            cleaned = re.sub(m.group(0), "", cleaned, flags=re.I)
        except ValueError:
            pass
    elif m := re.search(
        r"\b(on|by|due)\s+(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", lower
    ):
        month, day = int(m.group(2)), int(m.group(3))
        year = int(m.group(4)) if m.group(4) else ref.year
        if year < 100:
            year += 2000
        try:
            due = end_of_day(date(year, month, day))
            cleaned = re.sub(m.group(0), "", cleaned, flags=re.I)
        except ValueError:
            pass
    elif m := re.search(r"\bin\s+(\d+)\s+days?\b", lower):
        due = end_of_day(ref.date() + timedelta(days=int(m.group(1))))
        cleaned = re.sub(m.group(0), "", cleaned, flags=re.I)
    elif m := re.search(r"\bthis\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower):
        target = weekday_map[m.group(1)]
        days = (target - ref.weekday()) % 7
        due = end_of_day(ref.date() + timedelta(days=days))
        cleaned = re.sub(m.group(0), "", cleaned, flags=re.I)
    elif m := re.search(
        r"\b(?:for|on)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        lower,
    ):
        target = weekday_map[m.group(1)]
        days = (target - ref.weekday()) % 7
        due = end_of_day(ref.date() + timedelta(days=days))
        cleaned = re.sub(m.group(0), "", cleaned, flags=re.I)
    elif m := re.search(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*$",
        lower,
    ):
        target = weekday_map[m.group(1)]
        days = (target - ref.weekday()) % 7
        due = end_of_day(ref.date() + timedelta(days=days))
        cleaned = re.sub(m.group(0), "", cleaned, flags=re.I)

    # --- time-of-day fallback (NEW) ---
    tod_match = re.search(r"\b(morning|afternoon|evening|night)\b", lower)
    if tod_match:
        hour = TIME_OF_DAY[tod_match.group(1)]
        
        # If a date was already determined (e.g., tomorrow), keep its date component!
        base_date = due.date() if due else ref.date()
        
        due = datetime.combine(base_date, datetime.min.time()).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        cleaned = re.sub(tod_match.group(0), "", cleaned, flags=re.I)
    else:
        weekday_matches = list(
            re.finditer(
                r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                lower,
            )
        )
        if weekday_matches:
            m = weekday_matches[-1]
            target = weekday_map[m.group(1)]
            days = (target - ref.weekday()) % 7
            due = end_of_day(ref.date() + timedelta(days=days))
            cleaned = re.sub(m.group(0), "", cleaned, flags=re.I)

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—,.")
    return cleaned, due


def parse_event_timing(text: str, reference: Optional[datetime] = None) -> Tuple[str, Optional[datetime], Optional[datetime]]:
    """
    Parse title, start, and optional end from natural language.
    Returns (title, start_at, end_at).
    """
    ref = reference or datetime.now()
    lower = text.lower()
    end_at: Optional[datetime] = None
    start: Optional[datetime] = None

    duration_m = re.search(r"\bfor\s+(\d+)\s*(hour|hr|minute|min)s?\b", lower)
    extra_end = None
    if duration_m:
        n = int(duration_m.group(1))
        unit = duration_m.group(2)
        extra_end = timedelta(hours=n) if unit.startswith("h") else timedelta(minutes=n)
        text = re.sub(duration_m.group(0), "", text, flags=re.I)

    title, date_hint = parse_natural_due(text, ref)
    # --- FIX: interpret "evening today", "today evening", etc ---
    lower = text.lower()

    time_of_day = None
    if "morning" in lower:
        time_of_day = 9
    elif "afternoon" in lower:
        time_of_day = 14
    elif "evening" in lower:
        time_of_day = 18
    elif "night" in lower:
        time_of_day = 20

    if time_of_day:
        base = date_hint.date() if date_hint else ref.date()

        # If no explicit start time was parsed, set it
        if not start:
            start = datetime.combine(base, datetime.min.time()).replace(
                hour=time_of_day, minute=0, second=0, microsecond=0
            )
    base_date = date_hint.date() if date_hint else ref.date()

    range_times = parse_time_range(text, base_date)
    if range_times:
        start, end_at = range_times
        title = re.sub(
            r"(\d{1,2})\s*(?::|\s+)?(\d{2})?\s*(am|pm)?\s*(?:to|until|-)\s*"
            r"(\d{1,2})\s*(?::|\s+)?(\d{2})?\s*(am|pm)?",
            "",
            title,
            flags=re.I,
        ).strip(" -–—,.")

    # Time of day: "at 3pm", "at 14:30"
    time_m = re.search(
        r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
        text,
        re.I,
    )
    if time_m:
        hour = int(time_m.group(1))
        minute = int(time_m.group(2) or 0)
        ampm = (time_m.group(3) or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        elif not ampm and hour <= 7:
            hour += 12
        if start:
            start = start.replace(hour=hour, minute=minute, second=0, microsecond=0)
        else:
            start = ref.replace(hour=hour, minute=minute, second=0, microsecond=0)
        title = re.sub(time_m.group(0), "", title, flags=re.I).strip(" -–—,.")

    if start and start.hour == 23 and start.minute == 59:
        start = start.replace(hour=10, minute=0, second=0, microsecond=0)

    if start and extra_end:
        end_at = start + extra_end
    elif start:
        end_at = start + timedelta(hours=1)

    title = re.sub(r"\s+", " ", title).strip(" -–—,.")
    return title, start, end_at


def _normalize_priority(word: str) -> Optional[str]:
    w = word.lower().strip()
    if w in VALID_PRIORITIES:
        return w
    if w in ("urgent", "asap", "critical", "important"):
        return "high"
    if w in ("normal", "regular"):
        return "medium"
    if w in ("minor", "optional", "someday"):
        return "low"
    return None


def _normalize_status(phrase: str) -> Optional[str]:
    p = phrase.lower().strip().replace("-", " ")
    mapping = {
        "pending": "pending",
        "todo": "pending",
        "to do": "pending",
        "not started": "pending",
        "in progress": "in_progress",
        "in_progress": "in_progress",
        "started": "in_progress",
        "working": "in_progress",
        "doing": "in_progress",
        "completed": "completed",
        "complete": "completed",
        "done": "completed",
        "finished": "completed",
    }
    return mapping.get(p)


def _title_case(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    return s[0].upper() + s[1:]


def parse_task_payload(raw: str) -> Dict[str, Any]:
    """Split user text into title, description, priority, tags, due date."""
    text = raw.strip()
    priority = "medium"
    status = "pending"
    tags: List[str] = []

    _, due = parse_natural_due(text)

    if re.search(r"\b(urgent|asap|critical|high\s+priority|!important)\b", text, re.I):
        priority = "high"
    elif re.search(r"\b(low\s+priority|whenever|no rush|optional)\b", text, re.I):
        priority = "low"

    pri_inline = re.search(
        r"\bpriority\s+(high|medium|low|urgent|asap)\b", text, re.I
    )
    if pri_inline:
        p = _normalize_priority(pri_inline.group(1))
        if p:
            priority = p
        text = text[: pri_inline.start()] + text[pri_inline.end() :]

    status_m = re.search(
        r"\bstatus\s*[:=]\s*(pending|in\s*progress|in_progress|completed|done)\b",
        text,
        re.I,
    )
    if status_m:
        norm = _normalize_status(status_m.group(1))
        if norm:
            status = norm
        text = text[: status_m.start()].strip()

    pri_m = re.search(
        r"\bpriority\s*[:=]\s*(high|medium|low|urgent|asap)\b",
        text,
        re.I,
    )
    if pri_m:
        p = _normalize_priority(pri_m.group(1))
        if p:
            priority = p
        text = text[: pri_m.start()].strip()

    found_tags = re.findall(r"#([\w-]+)", text)
    if found_tags:
        tags = [t.strip().lower() for t in found_tags if t.strip()]
        for tag in found_tags:
            t = tag.lower()
            if t not in tags:
                tags.append(t)
        tags = list(dict.fromkeys(tags))
    text = re.sub(r"#([\w-]+)", "", text).strip()

    tags_m = re.search(r"\btags?\s*[:=]\s*(.+?)(?:\s*$|\s+(?:due|by|on)\s+)", text, re.I)
    if not tags_m:
        tags_m = re.search(r"\btags?\s*[:=]\s*(.+)$", text, re.I)
    if tags_m:
        for tag in re.split(r"[,;]", tags_m.group(1)):
            t = tag.strip().lower()
            if t and t not in tags:
                tags.append(t)
        text = text[: tags_m.start()].strip()

    description = ""
    desc_m = re.search(r"\bdescription\s*[:=]\s*(.+)$", text, re.I)
    if desc_m:
        description = desc_m.group(1).strip()
        text = text[: desc_m.start()].strip()
    else:
        for sep in (" — ", " – ", " - ", " | ", "; "):
            if sep in text:
                left, right = text.split(sep, 1)
                if len(left) >= 3 and len(right) >= 8:
                    text = left.strip()
                    description = right.strip()
                    break

    # remove priority phrases
    text = re.sub(r"\b(mid|medium|high|low)\s+priority\b", "", text, flags=re.I)

    # remove inline priority labels
    text = re.sub(r"\bpriority\s*[:=]\s*(high|medium|low)\b", "", text, flags=re.I)

    # remove time phrases BEFORE parsing (commented out to allow extraction later)
    # text = re.sub(r"\bat\s+\d{1,2}(?::\d{2})?\s*(am|pm)?\b", "", text, flags=re.I)

    # normalize spacing
    text = re.sub(r"\s+", " ", text).strip(" -–—,.")

    # cleanup spacing
    text = re.sub(r"\s+", " ", text).strip(" -–—,.")
    title, due_from_title = parse_natural_due(text)
    if due_from_title:
        due = due_from_title

    # Strip "at H:MM am/pm" or bare "H:MMam/pm" / "H pm" from the title and use it to refine the due time
    _time_m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", title, re.I)
    if not _time_m:
        _time_m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", title, re.I)
    if _time_m:
        _hour = int(_time_m.group(1))
        _minute = int(_time_m.group(2) or 0)
        _ampm = (_time_m.group(3) or "").lower()
        if _ampm == "pm" and _hour < 12:
            _hour += 12
        elif _ampm == "am" and _hour == 12:
            _hour = 0
        elif not _ampm and _hour <= 7:
            _hour += 12
        if due:
            due = due.replace(hour=_hour, minute=_minute, second=0, microsecond=0)
        else:
            due = datetime.now().replace(hour=_hour, minute=_minute, second=0, microsecond=0)
        title = re.sub(re.escape(_time_m.group(0)), "", title, flags=re.I)

    title = re.sub(
        r"\b(high|low)\s+priority\b",
        "",
        title,
        flags=re.I,
    ).strip()
    title = re.sub(r"\s+", " ", title).strip(" -–—,.")

    if not description and len(raw) > len(title) + 15:
        remainder = raw
        for bit in (title,):
            remainder = remainder.replace(bit, "", 1)
        remainder = re.sub(
            r"\b(due|by|tomorrow|today|tags?|priority|#)\S*",
            "",
            remainder,
            flags=re.I,
        ).strip(" -–—,.")
        if len(remainder) >= 12:
            description = remainder[:500]

    description = re.sub(
        r"\bpriority\s+(high|medium|low)\b", "", description, flags=re.I
    ).strip()
    description = re.sub(r"\s+", " ", description).strip(" -–—,.")

    if not tags:
        lower = raw.lower()
        for tag, keywords in AUTO_TAG_KEYWORDS.items():
            if any(k in lower for k in keywords):
                tags.append(tag)

    if len(title) > 72 and not description:
        cut = title[:72].rsplit(" ", 1)[0]
        description = title[len(cut) :].strip(" -–—:.")
        title = cut

    title = re.sub(r"\s+", " ", title).strip(" -–—,.")

    title = _title_case(title)

    if not description and title:
        description = f"Track and complete: {title}."

    return {
        "title": title,
        "description": description[:1000],
        "priority": priority,
        "status": status,
        "tags": tags[:8],
        "due_date": due,
    }


def serialize_task(t: TaskDB) -> Dict[str, Any]:
    return {
        "id": t.id,
        "type": "task",
        "title": t.title,
        "description": t.description or "",
        "status": t.status,
        "priority": t.priority,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "tags": t.tags.split(",") if t.tags else [],
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def serialize_event(e: CalendarEventDB) -> Dict[str, Any]:
    return {
        "id": e.id,
        "type": "event",
        "title": e.title,
        "description": e.description or "",
        "start": e.start_at.isoformat() if e.start_at else None,
        "end": e.end_at.isoformat() if e.end_at else None,
        "all_day": bool(e.all_day),
        "location": e.location or "",
        "color": e.color or "violet",
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def task_to_calendar_item(t: TaskDB) -> Dict[str, Any]:
    start = t.due_date or t.created_at
    if not start:
        return {}
    if isinstance(start, datetime) and start.hour == 0 and start.minute == 0:
        end = start.replace(hour=23, minute=59, second=59)
    else:
        end = start + timedelta(hours=1)
    return {
        "id": t.id,
        "type": "task",
        "title": t.title,
        "start": start.isoformat(),
        "end": end.isoformat() if isinstance(end, datetime) else start.isoformat(),
        "all_day": True,
        "status": t.status,
        "priority": t.priority,
        "description": t.description or "",
        "color": {"high": "red", "medium": "amber", "low": "emerald"}.get(t.priority, "violet"),
    }


class TaskManager:
    def create_task(
        self,
        db: Session,
        title: str,
        *,
        description: str = "",
        priority: str = "medium",
        status: str = "pending",
        due_date: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
    ) -> TaskDB:

        task = TaskDB(
            title=title.strip(),
            description=description,
            priority=priority if priority in PRIORITY_ORDER else "medium",
            status=status,
            due_date=due_date,
            tags=",".join(tags or []),
        )

        # 1. Stage object in session
        db.add(task)

        # 2. Commit to database
        db.commit()

        # 3. Refresh to load DB-generated fields (id, timestamps, etc.)
        db.refresh(task)

        # 4. ✅ DB confirmation (this is the correct place)
        exists = db.query(TaskDB).filter(TaskDB.id == task.id).first()
        if not exists:
            raise Exception("Task creation failed: not found in DB after commit")

        print("CREATED TASK CONFIRMED:", {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "status": task.status,
            "due_date": task.due_date,
            "tags": tags,
        })

        return task

    def create_event(
        self,
        db: Session,
        title: str,
        start_at: datetime,
        end_at: Optional[datetime] = None,
        *,
        description: str = "",
        all_day: bool = False,
        location: str = "",
        color: str = "violet",
    ) -> CalendarEventDB:
        if end_at is None:
            end_at = start_at + (timedelta(days=1) if all_day else timedelta(hours=1))
        event = CalendarEventDB(
            title=title.strip(),
            description=description,
            start_at=start_at,
            end_at=end_at,
            all_day=1 if all_day else 0,
            location=location,
            color=color,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    def find_task_by_title(
        self, db: Session, fragment: str, open_only: bool = True
    ) -> Optional[TaskDB]:
        fragment = fragment.strip().lower()
        if not fragment:
            return None
        q = db.query(TaskDB)
        if open_only:
            q = q.filter(TaskDB.status.in_(["pending", "in_progress"]))
        tasks = q.order_by(TaskDB.updated_at.desc()).all()

        for t in tasks:
            if t.title.lower() == fragment:
                return t
        for t in tasks:
            if fragment in t.title.lower():
                return t
        words = [w for w in fragment.split() if len(w) > 2]
        if words:
            best = None
            best_score = 0
            for t in tasks:
                title_l = t.title.lower()
                score = sum(1 for w in words if w in title_l)
                if score > best_score:
                    best_score = score
                    best = t
            if best_score >= max(1, len(words) // 2):
                return best
        return None

    async def _llm_refine_task_payload(
        self, raw: str, model: str, base: Dict[str, Any]
    ) -> Dict[str, Any]:
        prompt = f"""
            Convert the user's message into a task.

            Reply with exactly one line in this format:

            <task title>|<task description>|<priority>|<tag1,tag2>

            Rules:
            - Return actual values only.
            - Do NOT return labels.
            - Do NOT use the words TITLE or DESCRIPTION.
            - Title should be short (max 10 words).
            - Priority must be high, medium, or low.
            - Tags must be lowercase.

            User input: {raw}
            """

        try:
            response = (
                await ollama_client.generate(
                    model,
                    [{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
            ).strip()
            if response.startswith("[Error"):
                return base

            line = response.split("\n")[0].strip()
            parts = line.split("|")
            if len(parts) < 3:
                return base

            title = parts[0].strip()
            description = parts[1].strip()
            priority = _normalize_priority(parts[2].strip()) or base["priority"]

            # Reject placeholder/template outputs from the model
            bad_titles = {
                "title",
                "<title>",
                "<task title>",
                "task title",
                "headline",
            }

            bad_descriptions = {
                "description",
                "<description>",
                "<task description>",
                "task description",
            }

            if not title or title.lower() in bad_titles:
                title = base["title"]

            if not description or description.lower() in bad_descriptions:
                description = base["description"]
            extra_tags = []
            if len(parts) > 3 and parts[3].strip():
                extra_tags = [
                    t.strip().lower()
                    for t in parts[3].split(",")
                    if t.strip()
                ]

            tags = list(dict.fromkeys([*base.get("tags", []), *extra_tags]))[:8]

            return {
                **base,
                "title": _title_case(title[:120]),
                "description": description[:1000],
                "priority": priority,
                "tags": tags,
            }
        except Exception:
            return base

    def _format_task_created_message(self, task: TaskDB) -> str:
        tags = task.tags.split(",") if task.tags else []
        lines = [f"Created task: **{task.title}**"]
        lines.append(f"- Priority: **{task.priority}** · Status: {task.status}")
        if task.description:
            short = task.description[:160] + ("…" if len(task.description) > 160 else "")
            lines.append(f"- {short}")
        if tags:
            lines.append(f"- Tags: {', '.join(tags)}")
        if task.due_date:
            lines.append(f"- Due: {task.due_date.strftime('%Y-%m-%d')}")
        return "\n".join(lines)

    def _try_update_task_priority(self, text: str, db: Session) -> Optional[ActionResult]:
        patterns = [
            r"(?:set|change|update)\s+(?:the\s+)?priority\s+(?:of|for)\s+(.+?)\s+to\s+(high|medium|low|urgent|asap)",
            r"(?:set|change|update)\s+(.+?)\s+priority\s+to\s+(high|medium|low|urgent|asap)",
            r"make\s+(.+?)\s+(high|medium|low)\s+priority",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if not m:
                continue
            fragment, pri_word = m.group(1).strip(), m.group(2).strip()
            priority = _normalize_priority(pri_word)
            if not priority:
                continue
            task = self.find_task_by_title(db, fragment, open_only=False)
            if not task:
                return ActionResult(
                    "update_priority",
                    False,
                    f"No task found matching “{fragment}”.",
                )
            task.priority = priority
            task.updated_at = datetime.utcnow()
            db.commit()
            return ActionResult(
                "update_priority",
                True,
                f"**{task.title}** → priority **{priority}**",
                task.id,
                "task",
            )
        return None

    def _try_update_task_status(self, text: str, db: Session) -> Optional[ActionResult]:
        # --- in-progress: "start/begin working on X" ---
        m = re.search(r"(?:start|begin)\s+(?:working\s+on\s+)?(.+)$", text, re.I)
        if m:
            task = self.find_task_by_title(db, m.group(1).strip(), open_only=False)
            if task:
                task.status = "in_progress"
                task.updated_at = datetime.utcnow()
                db.commit()
                return ActionResult(
                    "update_status",
                    True,
                    f"**{task.title}** → status **in progress**",
                    task.id,
                    "task",
                )

        # --- explicit status update patterns ---
        patterns = [
            r"(?:set|change|update)\s+(?:the\s+)?status\s+(?:of|for)\s+(.+?)\s+to\s+"
            r"(pending|in\s*progress|in_progress|completed|done)",
            r"(?:mark|set)\s+(.+?)\s+as\s+(pending|in\s*progress|in_progress|completed|done|finished)",
            r"(?:move|set)\s+(.+?)\s+to\s+(in\s*progress|in_progress|pending|completed|done)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if not m:
                continue
            fragment = m.group(1).strip()
            status_word = m.group(2).strip()
            status = _normalize_status(status_word)
            if not status:
                continue
            task = self.find_task_by_title(db, fragment, open_only=False)
            if not task:
                return ActionResult(
                    "update_status",
                    False,
                    f"No task found matching “{fragment}”.",
                )
            task.status = status
            task.updated_at = datetime.utcnow()
            db.commit()
            label = status.replace("_", " ")
            return ActionResult(
                "update_status",
                True,
                f"**{task.title}** → status **{label}**",
                task.id,
                "task",
            )

        completion_patterns = [
            r"(?:i\s+)?(?:just\s+)?(?:finished|completed|wrapped\s+up|done\s+with)\s+(?:the\s+)?(.+?)[\.\ !]*$",
            r"(?:i\s+)?(?:just\s+)?done\s+(?:the\s+)?(.+?)[\.\ !]*$",
        ]
        for pat in completion_patterns:
            m = re.search(pat, text, re.I)
            if not m:
                continue
            fragment = m.group(1).strip()
            if len(fragment) < 3:
                continue
            task = self.find_task_by_title(db, fragment)
            if task:
                task.status = "completed"
                task.updated_at = datetime.utcnow()
                db.commit()
                return ActionResult(
                    "complete_task",
                    True,
                    f"Completed task: **{task.title}**",
                    task.id,
                    "task",
                )

        return None

    def _is_event_request(self, lower: str) -> bool:
        lower = normalize_calendar_text(lower)
        
        # CRITICAL FIX: If it mentions birth dates or past events, ignore calendar
        if re.search(r"\b(was born|birthday in \d{4}|born on|historical|remembers? that)\b", lower):
            return False
            
        if re.search(r"\b(task|todo)\b", lower) and not re.search(
            r"\b(event|meeting|appointment|(?:calendar|calender))\b", lower
        ):
            return False
        if re.search(r"\b(event|meeting|appointment|(?:calendar|calender))\b", lower):
            return True
        if re.search(r"\b(?:to|on|onto)\s+(?:my\s+)?(?:calendar|calender)\b", lower):
            return True
        if lower.startswith("book "):
            return True
        if lower.startswith("schedule ") and "task" not in lower:
            return True
        return False

    def _extract_put_on_calendar_body(self, text: str) -> Optional[str]:
        m = re.search(
            r"(?:add|put)\s+(.+?)\s+(?:to|on|onto)\s+(?:my\s+)?(?:calendar|calender)\b\s*(?:for\s+(.+))?$",
            text,
            re.I,
        )
        if m:
            title = m.group(1).strip()
            when = (m.group(2) or "").strip()
            return f"{title} {when}".strip()
        return None

    def _try_create_calendar_event(self, text: str, db: Session) -> Optional[ActionResult]:
        """Parse many phrasings and insert into calendar_events."""
        text = normalize_calendar_text(text)
        lower = text.lower()
        body: Optional[str] = None

        body = self._extract_put_on_calendar_body(text)

        extract_patterns = [
            r"(?:add|create|put)\s+(?:an?\s+)?event\s+(?:to\s+(?:the\s+)?calendar\s*)?(?:[:,]?\s*)(.+)$",
            r"(?:add|create|put)\s+(?:an?\s+)?(?:meeting|appointment)\s+(?:to\s+(?:the\s+)?calendar\s*)?(?:[:,]?\s*)(.+)$",
            r"(?:add|put)\s+(?:this|it)\s+on\s+(?:my\s+)?calendar[:\s]+(.+)$",
            r"(?:schedule|book)\s+(?:an?\s+)?(?:event|meeting|appointment)\s*(?:[:,]?\s*)(.+)$",
            r"^calendar[:\s]+(.+)$",
            r"^(?:meeting|appointment)[:\s]+(.+)$",
            r"^(?:add|create)\s+(?:to\s+)?calendar[:\s]+(.+)$",
            r"^schedule\s+(.+)$",
            r"^book\s+(.+)$",
        ]

        if not body:
            for pat in extract_patterns:
                m = re.search(pat, text, re.I)
                if m:
                    body = m.group(1).strip()
                    break

        if not body and self._is_event_request(lower):
            m = re.search(
                r"(?:event|meeting|appointment|calendar)\s+(?:for|about|called)?\s*[:\-]?\s*(.+)$",
                text,
                re.I,
            )
            if m:
                body = m.group(1).strip()

        if not body or len(body) < 2:
            return None

        return self._create_event_from_body(body, db)

    def _create_event_from_body(self, body: str, db: Session) -> Optional[ActionResult]:
        title, start, end = parse_event_timing(body)
        if len(title) < 2:
            return None

        if not start:
            _, date_hint = parse_natural_due(body, datetime.now())
            if date_hint:
                start = date_hint.replace(hour=10, minute=0, second=0, microsecond=0)
            else:
                start = datetime.now().replace(
                    hour=10, minute=0, second=0, microsecond=0
                ) + timedelta(days=1)
            end = start + timedelta(hours=1)

        event = self.create_event(db, title, start, end)
        end_note = ""
        if end and end != start + timedelta(hours=1):
            end_note = f" – {end.strftime('%I:%M %p').lstrip('0')}"
        when = start.strftime("%a %b %d, %Y %I:%M %p").lstrip("0").replace(" 0", " ")
        return ActionResult(
            "create_event",
            True,
            f"Added to calendar: **{event.title}** — {when}{end_note}",
            event.id,
            "event",
        )

    def _is_time_followup(self, text: str) -> bool:
        t = text.strip().lower()
        if parse_time_range(text):
            return True
        if re.search(r"\d{1,2}\s*(?::|\s+)\d{0,2}\s*(am|pm)", t):
            return True
        if re.search(r"\bfrom\s+\d", t) and re.search(r"\bto\s+\d", t):
            return True
        return False

    def _find_pending_task_request(
        self, history: List[Dict[str, str]]
    ) -> Optional[str]:
        """Find the most recent task title the user mentioned creating or talking about."""
        task_create_pat = re.compile(
            r"(?:add|create|new)\s+task[:\s]+(.+)|task[:\s]+(.+)|remind me to\s+(.+)|todo[:\s]+(.+)",
            re.I,
        )
        task_ref_pat = re.compile(
            r"(?:the\s+)?task\s+(?:called|named)\s+(.+)|"
            r"working on\s+(.+)|started\s+(.+)",
            re.I,
        )
        for msg in reversed(history):
            if msg.get("role") != "user":
                continue
            content_text = msg.get("content", "").strip()
            m = task_create_pat.search(content_text)
            if m:
                fragment = next(g for g in m.groups() if g)
                return fragment.strip()
            m = task_ref_pat.search(content_text)
            if m:
                fragment = next(g for g in m.groups() if g)
                return fragment.strip()
        return None

    def _find_pending_calendar_request(
        self, history: List[Dict[str, str]]
    ) -> Optional[str]:
        for msg in reversed(history):
            if msg.get("role") != "user":
                continue
            content = normalize_calendar_text(msg.get("content", "").strip())
            if not content or not self._is_event_request(content.lower()):
                continue
            body = self._extract_put_on_calendar_body(content)
            if body:
                return body
            m = re.search(
                r"(?:add|put)\s+(.+?)\s+(?:to|on)\s+(?:my\s+)?(?:calendar|calender)",
                content,
                re.I,
            )
            if m:
                rest = content[m.end() :].strip()
                title = m.group(1).strip()
                if rest.lower().startswith("for "):
                    return f"{title} {rest}"
                return title
        return None

    async def process_with_history(
        self,
        message: str,
        history: List[Dict[str, str]],
        db: Session,
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        text = normalize_calendar_text(message.strip())
        if not text:
            return []

        actions = await self.process_user_message(text, db, model=model)
        if actions:
            return actions

        if self._is_time_followup(text):
            pending = self._find_pending_calendar_request(history)
            if pending:
                combined = f"{pending} {text}"
                created = self._create_event_from_body(combined, db)
                if created:
                    return [created.to_dict()]

        if re.match(r"^(yes|yeah|yep|confirm|do it|go ahead)\.?!?$", text.lower()):
            pending = self._find_pending_calendar_request(history)
            if pending:
                created = self._create_event_from_body(pending, db)
                if created:
                    return [created.to_dict()]

        bare_done = re.match(
            r"^(?:yes[,\s]+)?(?:it['s\s]+)?(?:done|finished|completed|complete)[\.\!]*$",
            text.strip(),
            re.I,
        )
        if bare_done:
            pending_task = self._find_pending_task_request(history)
            if pending_task:
                task = self.find_task_by_title(db, pending_task)
                if task:
                    task.status = "completed"
                    task.updated_at = datetime.utcnow()
                    db.commit()
                    return [ActionResult(
                        "complete_task", True,
                        f"Completed task: **{task.title}**",
                        task.id, "task",
                    ).to_dict()]

        return []

    async def process_with_llm(
        self, text: str, db: Session, model: str
    ) -> List[Dict[str, Any]]:
        # Quick check to avoid calling LLM for non-scheduling chats
        lower = text.lower()
        has_time = bool(re.search(r"\b\d{1,2}(?::\d{2})?\s*(am|pm)?\b", lower))
        has_keyword = any(k in lower for k in [
            "task", "todo", "remind", "schedule", "calendar", "calender",
            "event", "meeting", "appointment", "priority", "status", "due",
            "today", "tomorrow", "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday", "jan", "feb", "mar", "apr", "may",
            "jun", "jul", "aug", "sep", "oct", "nov", "dec", "done", "finish",
            "complete", "move to", "reschedule", "cancel", "delete"
        ])
        if not (has_time or has_keyword):
            return []

        prompt = f"""You are a precise JSON extractor for a personal scheduling assistant.
Analyze the user's scheduling request: "{text}"

Respond with ONLY a JSON object of this structure. Do not include comments, descriptions, or markdown formatting (no ```json code blocks). 
If a field is not present or mentioned in the user's request, set it to null (or empty list for tags).

Schema:
{{
  "intent": "create_task" | "update_task_priority" | "update_task_status" | "complete_task" | "reschedule_task" | "create_event" | "delete_event" | "other",
  "title": "Clean title of the task/event (remove date, time, priority, tags, status words, and action prefixes like 'add task' or 'put on calendar')",
  "description": "Short description of the task/event if specified",
  "priority": "high" | "medium" | "low" | null,
  "status": "pending" | "in_progress" | "completed" | null,
  "date_phrase": "Raw date phrase if specified (e.g. 'tomorrow', 'next Monday', 'June 15th', 'Sunday')",
  "time_phrase": "Raw time/duration phrase if specified (e.g. 'at 10am', 'from 2 to 3 PM', '6:45pm to 7:45pm')",
  "tags": ["tag1", "tag2"],
  "target_title": "Title/fragment of existing task/event to update/complete/delete"
}}

Examples:
1. User: "add task call mom next Monday high priority"
   JSON: {{
     "intent": "create_task",
     "title": "Call Mom",
     "description": null,
     "priority": "high",
     "status": "pending",
     "date_phrase": "next Monday",
     "time_phrase": null,
     "tags": ["mom"],
     "target_title": "Call Mom"
   }}
2. User: "dentist on June 15 from 2 to 3 PM"
   JSON: {{
     "intent": "create_event",
     "title": "Dentist Appointment",
     "description": null,
     "priority": null,
     "status": null,
     "date_phrase": "June 15th",
     "time_phrase": "from 2 to 3 PM",
     "tags": ["dentist"],
     "target_title": null
   }}
3. User: "change priority of write report to low"
   JSON: {{
     "intent": "update_task_priority",
     "title": null,
     "description": null,
     "priority": "low",
     "status": null,
     "date_phrase": null,
     "time_phrase": null,
     "tags": [],
     "target_title": "write report"
   }}
"""

        try:
            res = await ollama_client.generate(
                model,
                [{"role": "user", "content": prompt}],
                format="json",
                temperature=0.0
            )
            data = json.loads(res.strip())
        except Exception as e:
            print(f"Ollama scheduling extraction error: {e}")
            return []

        if not data or not isinstance(data, dict):
            return []

        # Check for placeholder text (indicates small model hallucination of prompt schema)
        def is_placeholder(val):
            if not val or not isinstance(val, str):
                return False
            placeholders = ["clean title", "e.g.", "short description", "title/fragment", "raw date", "raw time"]
            return any(p in val.lower() for p in placeholders)

        if is_placeholder(data.get("title")) or is_placeholder(data.get("target_title")):
            print("Placeholder detected in Ollama output, falling back to regex")
            return []

        intent = data.get("intent")
        if intent not in ("create_task", "complete_task", "update_task_priority", "update_task_status", "reschedule_task", "create_event", "delete_event"):
            return []

        # Helper to capitalize title
        def format_title(val):
            if not val or not isinstance(val, str):
                return ""
            v = val.strip().strip(" -–—,.")
            if not v:
                return ""
            return v[0].upper() + v[1:]

        # Handle complete_task
        if intent == "complete_task":
            target = data.get("target_title") or data.get("title")
            if not target:
                return []
            task = self.find_task_by_title(db, target)
            if task:
                task.status = "completed"
                task.updated_at = datetime.utcnow()
                db.commit()
                return [ActionResult(
                    "complete_task",
                    True,
                    f"Completed task: **{task.title}**",
                    task.id,
                    "task"
                ).to_dict()]
            else:
                return [ActionResult(
                    "complete_task",
                    False,
                    f"Couldn't find an open task matching “{target}”."
                ).to_dict()]

        # Handle update_task_priority
        if intent == "update_task_priority":
            target = data.get("target_title") or data.get("title")
            priority = data.get("priority")
            if not target or not priority:
                return []
            priority = _normalize_priority(priority)
            if not priority:
                return []
            task = self.find_task_by_title(db, target, open_only=False)
            if task:
                task.priority = priority
                task.updated_at = datetime.utcnow()
                db.commit()
                return [ActionResult(
                    "update_priority",
                    True,
                    f"**{task.title}** → priority **{priority}**",
                    task.id,
                    "task"
                ).to_dict()]
            else:
                return [ActionResult(
                    "update_priority",
                    False,
                    f"No task found matching “{target}”."
                ).to_dict()]
        if intent == "update_task_status":
            target = data.get("target_title") or data.get("title")
            status = data.get("status")
            if not target or not status:
                return []
            
            norm_status = _normalize_status(status)
            if not norm_status:
                return []
                
            task = self.find_task_by_title(db, target, open_only=False)
            if task:
                task.status = norm_status
                task.updated_at = datetime.utcnow()
                db.commit()
                return [ActionResult(
                    "update_status", 
                    True, 
                    f"Updated status of **{task.title}** to **{norm_status.replace('_', ' ')}**", 
                    task.id, 
                    "task"
                ).to_dict()]
            else:
                return [ActionResult(
                    "update_status", 
                    False, 
                    f"Couldn't find a task matching “{target}”."
                ).to_dict()]
        # Handle reschedule_task
        if intent == "reschedule_task":
            target = data.get("target_title") or data.get("title")
            if not target:
                return []
            task = self.find_task_by_title(db, target)
            if not task:
                return [ActionResult(
                    "reschedule_task",
                    False,
                    f"No task found matching “{target}”."
                ).to_dict()]
            due = None
            if data.get("date_phrase"):
                _, due = parse_natural_due(data["date_phrase"])
            if due and data.get("time_phrase"):
                time_m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", data["time_phrase"], re.I)
                if not time_m:
                    time_m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", data["time_phrase"], re.I)
                if time_m:
                    hour = int(time_m.group(1))
                    minute = int(time_m.group(2) or 0)
                    ampm = (time_m.group(3) or "").lower()
                    if ampm == "pm" and hour < 12:
                        hour += 12
                    elif ampm == "am" and hour == 12:
                        hour = 0
                    elif not ampm and hour <= 7:
                        hour += 12
                    due = due.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if due:
                task.due_date = due
                task.updated_at = datetime.utcnow()
                db.commit()
                return [ActionResult(
                    "reschedule_task",
                    True,
                    f"Updated **{task.title}** → due {due.strftime('%Y-%m-%d')}",
                    task.id,
                    "task"
                ).to_dict()]
            else:
                return [ActionResult(
                    "reschedule_task",
                    False,
                    f"Could not parse new date for “{target}”."
                ).to_dict()]

        # Handle delete_event
        if intent == "delete_event":
            target = data.get("target_title") or data.get("title")
            if not target:
                return []
            event = db.query(CalendarEventDB).filter(CalendarEventDB.title.like(f"%{target}%")).order_by(CalendarEventDB.created_at.desc()).first()
            if event:
                db.delete(event)
                db.commit()
                return [ActionResult(
                    "delete_event",
                    True,
                    f"Removed from calendar: **{event.title}**",
                    event.id,
                    "event"
                ).to_dict()]
            else:
                return [ActionResult(
                    "delete_event",
                    False,
                    f"Couldn't find calendar event matching “{target}”."
                ).to_dict()]

        # Handle create_task
        if intent == "create_task":
            title = format_title(data.get("title"))
            if not title or len(title) < 2:
                title = format_title(text)

            due_date = None
            if data.get("date_phrase"):
                _, due_date = parse_natural_due(data["date_phrase"])
                if due_date and data.get("time_phrase"):
                    time_m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", data["time_phrase"], re.I)
                    if not time_m:
                        time_m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", data["time_phrase"], re.I)
                    if time_m:
                        hour = int(time_m.group(1))
                        minute = int(time_m.group(2) or 0)
                        ampm = (time_m.group(3) or "").lower()
                        if ampm == "pm" and hour < 12:
                            hour += 12
                        elif ampm == "am" and hour == 12:
                            hour = 0
                        elif not ampm and hour <= 7:
                            hour += 12
                        due_date = due_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            elif data.get("time_phrase"):
                _, due_date = parse_natural_due("today")
                time_m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", data["time_phrase"], re.I)
                if not time_m:
                    time_m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", data["time_phrase"], re.I)
                if time_m:
                    hour = int(time_m.group(1))
                    minute = int(time_m.group(2) or 0)
                    ampm = (time_m.group(3) or "").lower()
                    if ampm == "pm" and hour < 12:
                        hour += 12
                    elif ampm == "am" and hour == 12:
                        hour = 0
                    elif not ampm and hour <= 7:
                        hour += 12
                    due_date = due_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # Auto-tag keywords if tags empty
            tags = data.get("tags") or []
            if not tags:
                lower_title = title.lower()
                for tag, keywords in AUTO_TAG_KEYWORDS.items():
                    if any(k in lower_title for k in keywords):
                        tags.append(tag)

            task = self.create_task(
                db,
                title,
                description=data.get("description") or f"Track and complete: {title}.",
                priority=data.get("priority") or "medium",
                status=data.get("status") or "pending",
                due_date=due_date,
                tags=tags
            )
            return [ActionResult(
                "create_task",
                True,
                self._format_task_created_message(task),
                task.id,
                "task"
            ).to_dict()]

        # Handle create_event
        if intent == "create_event":
            title = format_title(data.get("title"))
            if not title or len(title) < 2:
                title = format_title(text)

            base_date = None
            if data.get("date_phrase"):
                _, date_hint = parse_natural_due(data["date_phrase"])
                if date_hint:
                    base_date = date_hint.date()
            if not base_date:
                base_date = datetime.now().date()

            start = None
            end_at = None
            if data.get("time_phrase"):
                range_times = parse_time_range(data["time_phrase"], base_date)
                if range_times:
                    start, end_at = range_times
                else:
                    time_m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", data["time_phrase"], re.I)
                    if not time_m:
                        time_m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", data["time_phrase"], re.I)
                    if time_m:
                        hour = int(time_m.group(1))
                        minute = int(time_m.group(2) or 0)
                        ampm = (time_m.group(3) or "").lower()
                        if ampm == "pm" and hour < 12:
                            hour += 12
                        elif ampm == "am" and hour == 12:
                            hour = 0
                        elif not ampm and hour <= 7:
                            hour += 12
                        start = datetime.combine(base_date, datetime.min.time()).replace(
                            hour=hour, minute=minute, second=0, microsecond=0
                        )

            if not start:
                # Default to tomorrow at 10 AM
                start = datetime.combine(base_date, datetime.min.time()).replace(
                    hour=10, minute=0, second=0, microsecond=0
                )
                if start < datetime.now():
                    start += timedelta(days=1)

            if not end_at:
                end_at = start + timedelta(hours=1)

            event = self.create_event(
                db,
                title,
                start,
                end_at,
                description=data.get("description") or "",
                location=data.get("location") or "",
                color=data.get("color") or "violet"
            )

            end_note = ""
            if end_at and end_at != start + timedelta(hours=1):
                end_note = f" – {end_at.strftime('%I:%M %p').lstrip('0')}"
            when = start.strftime("%a %b %d, %Y %I:%M %p").lstrip("0").replace(" 0", " ")

            return [ActionResult(
                "create_event",
                True,
                f"Added to calendar: **{event.title}** — {when}{end_note}",
                event.id,
                "event"
            ).to_dict()]

        return []

    async def process_user_message(
        self, message: str, db: Session, model: Optional[str] = None
        ) -> List[Dict[str, Any]]:
        text = normalize_calendar_text(message.strip())
        if not text:
            return []

        # FIX: Memory/save commands must never create tasks or events
        MEMORY_TRIGGERS = (
            "remember ", "remember that", "save this", "store this",
            "note that", "keep in mind", "fyi ", "don't forget",
            "memorize", "add this to memory"
        )
        if any(text.lower().startswith(t) for t in MEMORY_TRIGGERS):
            return []

        # --- LLM Parsing First ---
        if model:
            try:
                # FIX: Also guard LLM path against memory commands
                lower_check = text.lower()
                is_memory_command = any(lower_check.startswith(t) for t in MEMORY_TRIGGERS)
                if not is_memory_command:
                    llm_actions = await self.process_with_llm(text, db, model)
                    if llm_actions:
                        return llm_actions
            except Exception as e:
                print(f"Ollama scheduling integration fallback: {e}")

        results: List[ActionResult] = []
        lower = text.lower()

        # --- Calendar events first (when it sounds like an event, not a task) ---
        if self._is_event_request(lower):
            created = self._try_create_calendar_event(text, db)
            if created:
                return [created.to_dict()]

        # --- Task updates ---
        updated = self._try_update_task_priority(text, db)
        if updated:
            return [updated.to_dict()]

        updated = self._try_update_task_status(text, db)
        if updated:
            return [updated.to_dict()]

        # --- Create task ---
        create_match = None
        for pat in [
            r"^(?:add|create|new)\s+(?:a\s+)?task\s*[:\s]\s*(.+)$",
            r"^task[:\s]+(.+)$",
            r"^remind me to (.+)$",
            r"^todo[:\s]+(.+)$",
            r"^i need to (.+)$",
        ]:
            m = re.search(pat, text, re.I)
            if m:
                create_match = m.group(1).strip()
                break

        if not create_match and len(text) < 80:
            _is_question = text.strip().endswith("?") or re.match(r"^(what|how|when|where|why|who|can|could|would|should|is|are|do|does)", text, re.I)
            _has_action_verb = re.search(
                r"^(?:go\s+to|call|email|text|buy|get|pick\s+up|visit|meet|study|"
                r"read|write|review|fix|send|check|clean|pay|book|finish|submit|"
                r"prepare|schedule|update|run|gym|workout|dentist|doctor)\b",
                text, re.I
            )
            if _has_action_verb and not _is_question and not self._is_event_request(lower):
                create_match = text

        if create_match and len(create_match.strip()) > 1:
            payload = parse_task_payload(create_match)
            if len(payload["title"]) >= 2:
                if model:
                    payload = await self._llm_refine_task_payload(
                        create_match, model, payload
                    )
                task = self.create_task(
                    db,
                    payload["title"],
                    description=payload["description"],
                    priority=payload["priority"],
                    status=payload["status"],
                    due_date=payload["due_date"],
                    tags=payload["tags"],
                )
                results.append(
                    ActionResult(
                        "create_task",
                        True,
                        self._format_task_created_message(task),
                        task.id,
                        "task",
                    )
                )
                return [r.to_dict() for r in results]

        for pat in [
            r"(?:^|\b)(?:mark|complete|finish|done\s+with)\s+(.+?)(?:\s+as\s+done)?[\.!]*$",
            r"(?:^|\b)(?:done|finished)\s+(?:the\s+)?(.+?)[\.!]*$",
        ]:
            m = re.search(pat, text, re.I)
            if m:
                fragment = m.group(1).strip()
                if len(fragment) < 3:
                    continue
                task = self.find_task_by_title(db, fragment)
                if task:
                    task.status = "completed"
                    task.updated_at = datetime.utcnow()
                    db.commit()
                    results.append(
                        ActionResult(
                            "complete_task",
                            True,
                            f"Completed task: **{task.title}**",
                            task.id,
                            "task",
                        )
                    )
                else:
                    results.append(
                        ActionResult(
                            "complete_task",
                            False,
                            f"Couldn't find an open task matching \"{fragment}\".",
                        )
                    )
                return [r.to_dict() for r in results]

        created = self._try_create_calendar_event(text, db)
        if created:
            return [created.to_dict()]

        if re.search(r"\b(?:reschedule|move|set due|due date)\b", lower):
            m = re.match(
                r"^(?:reschedule|move|set due(?:\s+date)?(?:\s+for)?)\s+(.+?)\s+to\s+(.+)$",
                text,
                re.I,
            )
            if m:
                fragment, when = m.group(1).strip(), m.group(2).strip()
                _, due = parse_natural_due(when, reference=datetime.now())
                if not due:
                    _, due = parse_natural_due(f"due {when}")
                task = self.find_task_by_title(db, fragment)
                if task and due:
                    task.due_date = due
                    task.updated_at = datetime.utcnow()
                    db.commit()
                    results.append(
                        ActionResult(
                            "reschedule_task",
                            True,
                            f"Updated **{task.title}** → due {due.strftime('%Y-%m-%d')}",
                            task.id,
                            "task",
                        )
                    )
                    return [r.to_dict() for r in results]

        return [r.to_dict() for r in results]

    def infer_date_range(self, query: str) -> Tuple[datetime, datetime]:
        now = datetime.now()
        lower = query.lower()
        start = datetime.combine(now.date(), datetime.min.time())
        end = start + timedelta(days=7)

        if re.search(r"\btoday\b", lower):
            end = start + timedelta(days=1)
        elif re.search(r"\btomorrow\b", lower):
            start = start + timedelta(days=1)
            end = start + timedelta(days=1)
        elif re.search(r"\bthis week\b", lower):
            end = start + timedelta(days=7)
        elif re.search(r"\bnext week\b", lower):
            start = start + timedelta(days=(7 - now.weekday()))
            end = start + timedelta(days=7)
        elif re.search(r"\bthis month\b", lower):
            last = monthrange(now.year, now.month)[1]
            end = datetime(now.year, now.month, last, 23, 59, 59)

        return start, end

    def get_calendar_items(
        self,
        db: Session,
        start: datetime,
        end: datetime,
        *,
        include_completed_tasks: bool = False,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        task_q = db.query(TaskDB).filter(TaskDB.due_date.isnot(None))
        if not include_completed_tasks:
            task_q = task_q.filter(TaskDB.status != "completed")
        for t in task_q.all():
            if t.due_date and start <= t.due_date <= end:
                item = task_to_calendar_item(t)
                if item:
                    items.append(item)

        events = (
            db.query(CalendarEventDB)
            .filter(CalendarEventDB.start_at <= end, CalendarEventDB.end_at >= start)
            .all()
        )
        for e in events:
            items.append({
                **serialize_event(e),
                "start": e.start_at.isoformat(),
                "end": e.end_at.isoformat() if e.end_at else e.start_at.isoformat(),
            })

        items.sort(key=lambda x: x.get("start") or "")
        return items

    def build_schedule_context(
        self, db: Session, query: str, intent: str, *, full: bool = False
    ) -> Tuple[str, List[str]]:
        """Rich schedule context for the model."""
        now = datetime.now()
        today_start = datetime.combine(now.date(), datetime.min.time())
        week_end = today_start + timedelta(days=7)

        sources: List[str] = []
        sections: List[str] = []

        open_tasks = (
            db.query(TaskDB)
            .filter(TaskDB.status.in_(["pending", "in_progress"]))
            .all()
        )
        open_tasks.sort(
            key=lambda t: (
                PRIORITY_ORDER.get(t.priority, 9),
                t.due_date or datetime.max,
            )
        )

        overdue = []
        due_today = []
        due_week = []
        no_date = []

        for t in open_tasks:
            if t.due_date:
                d = t.due_date.date() if isinstance(t.due_date, datetime) else t.due_date
                if d < now.date():
                    overdue.append(t)
                elif d == now.date():
                    due_today.append(t)
                elif t.due_date <= week_end:
                    due_week.append(t)
            else:
                no_date.append(t)

        # Always-on snapshot (compact)
        snapshot_parts = []
        if overdue:
            snapshot_parts.append(f"{len(overdue)} overdue")
        if due_today:
            snapshot_parts.append(f"{len(due_today)} due today")
        if due_week:
            snapshot_parts.append(f"{len(due_week)} due this week")
        upcoming_events = (
            db.query(CalendarEventDB)
            .filter(CalendarEventDB.start_at >= now, CalendarEventDB.start_at <= week_end)
            .order_by(CalendarEventDB.start_at)
            .limit(5)
            .all()
        )
        if upcoming_events:
            snapshot_parts.append(f"{len(upcoming_events)} upcoming events")

        if open_tasks and not snapshot_parts:
            snapshot_parts.append(f"{len(open_tasks)} open")

        planning_intent = intent in ("planning", "calendar")
        has_schedule_keyword = bool(re.search(
            r"\b(calendar|schedule|agenda|meeting|appointment|today|tomorrow|week|month|plan|focus|priority|overdue|task|todo)\b",
            query.lower(),
        ))

        if (snapshot_parts or full or open_tasks) and (full or planning_intent or has_schedule_keyword):
            lines = [f"**Now:** {now.strftime('%A %Y-%m-%d %H:%M')}"]
            if snapshot_parts:
                lines.append(f"**Summary:** {', '.join(snapshot_parts)}")
            sections.append("### Schedule snapshot\n" + "\n".join(lines))
            sources.append("schedule_snapshot")

        if not (full or planning_intent or has_schedule_keyword):
            return "\n\n".join(sections), sources

        if overdue:
            lines = [
                f"- ⚠️ [{t.priority}] {t.title} (was due {t.due_date.strftime('%Y-%m-%d')})"
                for t in overdue[:8]
            ]
            sections.append("### Overdue\n" + "\n".join(lines))

        if due_today:
            lines = [
                f"- [{t.priority}] {t.title}" + (f" — {t.description[:80]}" if t.description else "")
                for t in due_today[:10]
            ]
            sections.append("### Due today\n" + "\n".join(lines))

        range_start, range_end = self.infer_date_range(query)
        week_tasks = [t for t in open_tasks if t.due_date and range_start <= t.due_date <= range_end]
        if week_tasks and not due_today:
            lines = [
                f"- {t.due_date.strftime('%a %m/%d')} [{t.priority}] {t.title}"
                for t in week_tasks[:12]
            ]
            sections.append(
                f"### Tasks in range ({range_start.date()} → {range_end.date()})\n"
                + "\n".join(lines)
            )

        if no_date and (planning_intent or calendar_keywords):
            lines = [f"- [{t.priority}] {t.title}" for t in no_date[:6]]
            sections.append("### Backlog (no due date)\n" + "\n".join(lines))

        if upcoming_events or intent == "calendar":
            evts = (
                db.query(CalendarEventDB)
                .filter(CalendarEventDB.start_at >= range_start, CalendarEventDB.start_at <= range_end)
                .order_by(CalendarEventDB.start_at)
                .limit(15)
                .all()
            )
            if evts:
                lines = []
                for e in evts:
                    loc = f" @ {e.location}" if e.location else ""
                    lines.append(
                        f"- {e.start_at.strftime('%a %m/%d %H:%M')} **{e.title}**{loc}"
                    )
                sections.append("### Calendar events\n" + "\n".join(lines))
                sources.append("calendar_events")

        if open_tasks and planning_intent:
            sources.append("tasks")

        return "\n\n".join(sections), list(dict.fromkeys(sources))

    def suggest_daily_plan(self, db: Session) -> str:
        """Text block for 'what should I focus on' without extra keywords."""
        ctx, _ = self.build_schedule_context(db, "today plan focus", "planning", full=True)
        return ctx


task_manager = TaskManager()