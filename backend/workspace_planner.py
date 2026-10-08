"""Conservative structured plans; only explicit, validated relative reminders run."""
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_DURATION = 365 * 24 * 60 * 60
REMINDER_QUESTION = "What should I remind you about, and in how many seconds, minutes, or hours?"
TIME_QUESTION = "In how many seconds, minutes, or hours should I remind you?"
BOUNDS_QUESTION = "What short label and delay between 1 second and 365 days should I use?"
_POLITE = re.compile(r"^(?:(?:please|(?:can|could|would|will)\s+(?:you|u))\s+)+", re.I)
_PREFIX = re.compile(r"^(?:remind\s+me\b|(?:add|create|set|start)\s+(?:an?\s+)?(?:new\s+)?(?:reminder|timer)\b)", re.I)
_UNITS = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
          "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
          "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600}
_PART = re.compile(r"(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)\b", re.I)


class ReminderInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=200)
    duration_seconds: int = Field(strict=True, ge=1, le=MAX_DURATION)

    @field_validator("label")
    @classmethod
    def nonempty_label(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("A reminder label is required")
        return value


def is_reminder_request(message):
    return bool(_PREFIX.match(_POLITE.sub("", message.strip())))


def reminder_followup(message, history):
    """Resume our own timing clarification, without treating unrelated chat as permission."""
    if not history or history[-1].get("role") != "assistant":
        return None
    question = history[-1].get("content", "").strip()
    if question not in {TIME_QUESTION, REMINDER_QUESTION, BOUNDS_QUESTION}:
        return None
    if re.fullmatch(r"(?:yes|yeah|sure|ok(?:ay)?|do it|go ahead)[.!?]*", message, re.I):
        return "", question
    if not re.match(r"^(?:(?:in|after|for)\s+)?(?:(?:like|about|around)\s+)?[-\d]", message, re.I):
        return None
    previous = next((turn["content"] for turn in reversed(history[:-1])
                     if turn.get("role") == "user" and is_reminder_request(turn.get("content", ""))), "")
    text = _POLITE.sub("", previous.strip())
    prefix = _PREFIX.match(text)
    if not prefix:
        return "", REMINDER_QUESTION
    delay = re.sub(r"^(?:in|after|for)\s+", "", message, flags=re.I)
    if "timer" in prefix.group().lower():
        title = re.search(r"\s+to\s+(.+)$", text[prefix.end():], re.I)
        return f"set a timer for {delay}" + (f" to {title.group(1)}" if title else ""), ""
    label = re.sub(r"^(?:to|for)\s+", "", text[prefix.end():].strip(" :"), flags=re.I)
    label = re.split(r"\s+(?:in\b|at\s+\d|tomorrow\b|today\b|tonight\b|every\b|next\s+(?:week|month|year)\b)", label, maxsplit=1, flags=re.I)[0]
    # Other absolute/conditional formulations need an explicit restatement.
    if re.search(r"\bwhen\b|\bon\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d)\b", label, re.I):
        return "", REMINDER_QUESTION
    if not label:
        return "", REMINDER_QUESTION
    return f"remind me to {label} in {delay}", ""


def reminder_plan(message):
    text = _POLITE.sub("", message.strip())
    prefix = _PREFIX.match(text)
    plan = {"intent": "create_reminder", "capability_id": "timer", "inputs": {},
            "confidence": 0.0, "explanation": "A relative delay and a label are required."}
    if not prefix:
        return plan, REMINDER_QUESTION
    body = text[prefix.end():].strip(" :")
    # Support 'remind me to X in 30s' and 'set a timer for 30 seconds [to X]'.
    if "timer" in prefix.group().lower():
        match = re.fullmatch(r"(?:for\s+)?(.+?)(?:\s+(?:to|for)\s+(.+))?", body, re.I)
        delay, label = (match.group(1), match.group(2) or "Timer") if match else ("", "")
    else:
        match = re.fullmatch(r"(?:to\s+|for\s+)?(.+?)\s+in\s+(.+)", body, re.I)
        label, delay = (match.group(1), match.group(2)) if match else ("", "")
    delay = delay.rstrip(".!?").strip()
    delay = re.sub(r"^(?:like|about|around)\s+", "", delay, flags=re.I)
    if len(delay) > 200:
        return plan, TIME_QUESTION
    parts = list(_PART.finditer(delay))
    residue = _PART.sub("", delay)
    if not parts or re.sub(r"(?:\band\b|[,\s])", "", residue):
        return plan, TIME_QUESTION if body else REMINDER_QUESTION
    seconds = sum(int(part.group(1)) * _UNITS[part.group(2).lower()] for part in parts)
    label = label.strip().rstrip(".!?")
    if not label or len(label) > 200 or not 1 <= seconds <= MAX_DURATION:
        return plan, BOUNDS_QUESTION
    inputs = ReminderInputs(label=label[0].upper() + label[1:], duration_seconds=seconds)
    plan.update(inputs=inputs.model_dump(), confidence=1.0,
                explanation="Explicit reminder request with a validated relative duration.")
    return plan, ""
