"""Validated, topologically ordered workflows over a small set of local handlers."""
from datetime import datetime
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from workspace_planner import ReminderInputs, reminder_plan, reminder_followup, TIME_QUESTION

WORKFLOW_QUESTION = "Which task, relative reminder, or notification steps should this workflow contain?"
WORKFLOW_TIME_QUESTION = "What relative delay should the workflow reminder use, in seconds, minutes, or hours?"
Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")]


class Inputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def trim_strings(cls, value, info):
        if isinstance(value, str):
            value = value.strip()
            if not value and info.field_name not in {"description", "location"}:
                raise ValueError("Text must not be empty")
        return value

    @field_validator("due_date", "start_at", "end_at", check_fields=False)
    @classmethod
    def local_dates(cls, value):
        # Task/calendar dates follow their existing local-time storage convention.
        return value.astimezone().replace(tzinfo=None) if value and value.tzinfo else value


class TaskInputs(Inputs):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    priority: Literal["low", "medium", "high"] = "medium"
    status: Literal["pending", "in_progress", "completed"] = "pending"
    due_date: datetime | None = None
    tags: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(default_factory=list, max_length=20)


class CalendarInputs(Inputs):
    title: str = Field(min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime
    description: str = Field(default="", max_length=2000)
    location: str = Field(default="", max_length=200)
    all_day: bool = False

    @model_validator(mode="after")
    def valid_dates(self):
        if self.end_at <= self.start_at:
            raise ValueError("Calendar end must be after start")
        return self


class LinkedReminderInputs(ReminderInputs):
    task_step_id: Key | None = None


class WaitInputs(Inputs):
    reminder_step_id: Key
    until: Literal["due", "completed"] = "due"


class NotificationInputs(Inputs):
    message: str = Field(min_length=1, max_length=1000)


class Step(Inputs):
    id: Key
    depends_on: list[Key] = Field(default_factory=list, max_length=20)


class TaskStep(Step):
    action: Literal["create_task"]
    inputs: TaskInputs


class CalendarStep(Step):
    action: Literal["create_calendar_event"]
    inputs: CalendarInputs


class ReminderStep(Step):
    action: Literal["create_reminder"]
    inputs: LinkedReminderInputs


class WaitStep(Step):
    action: Literal["wait_for_reminder"]
    inputs: WaitInputs


class NotificationStep(Step):
    action: Literal["notify"]
    inputs: NotificationInputs


WorkflowStep = Annotated[TaskStep | CalendarStep | ReminderStep | WaitStep | NotificationStep,
                         Field(discriminator="action")]
step_adapter = TypeAdapter(WorkflowStep)


class WorkflowPlan(Inputs):
    title: str = Field(min_length=1, max_length=200)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def valid_graph(self):
        seen = {}
        for step in self.steps:
            if step.id in seen or len(set(step.depends_on)) != len(step.depends_on):
                raise ValueError("Step IDs and dependencies must be unique")
            if any(key not in seen for key in step.depends_on):
                raise ValueError("Dependencies must name earlier steps; cycles and forward references are not allowed")
            if isinstance(step, ReminderStep) and step.inputs.task_step_id:
                key, expected = step.inputs.task_step_id, TaskStep
            elif isinstance(step, WaitStep):
                key, expected = step.inputs.reminder_step_id, ReminderStep
            else:
                key = None
            if key and (key not in step.depends_on or not isinstance(seen.get(key), expected)):
                raise ValueError("Linked references must name a direct dependency of the correct type")
            seen[step.id] = step
        return self


class WorkflowCreate(Inputs):
    plan: WorkflowPlan
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=100)


_POLITE = re.compile(r"^(?:(?:please|(?:can|could|would|will)\s+(?:you|u))\s+)+", re.I)
_WORKFLOW = re.compile(r"^(?:(?:create|start|run|add)\s+(?:a\s+)?)?workflow\s*[:\s]*", re.I)
_TASK = re.compile(r"^(?:add|create)\s+(?:a\s+)?(?:new\s+)?(?:task|todo|to-do)\b\s*(?:(?:to|for)\s+|:\s*)?", re.I)
_START = re.compile(r"^(?:(?:add|create)\s+(?:a\s+)?(?:task|todo|to-do)\b|remind\s+me\b|set\s+(?:a\s+)?timer\b)", re.I)
_SEPARATOR = re.compile(r"[,;]?\s+(and then|then|and)\s+(?=(?:(?:please|(?:can|could|would|will)\s+(?:you|u))\s+)*(?:remind|add|create|set|notify|tell|delete|email|send)\b)", re.I)


def is_workflow_request(message):
    text = _POLITE.sub("", message.strip())
    return bool(_WORKFLOW.match(text) or (_START.match(text) and _SEPARATOR.search(text)))


def workflow_followup(message, history):
    if not history or history[-1].get("role") != "assistant" or history[-1].get("content", "").strip() != WORKFLOW_TIME_QUESTION:
        return None
    if re.fullmatch(r"(?:yes|yeah|sure|ok(?:ay)?|do it|go ahead)[.!?]*", message, re.I):
        return "", WORKFLOW_TIME_QUESTION
    if not re.match(r"^(?:(?:in|after|for)\s+)?(?:(?:like|about|around)\s+)?[-\d]", message, re.I):
        return None
    original = next((turn["content"] for turn in reversed(history[:-1])
                     if turn.get("role") == "user" and is_workflow_request(turn.get("content", ""))), "")
    pieces = _SEPARATOR.split(_WORKFLOW.sub("", _POLITE.sub("", original.strip()), count=1))
    invalid = [index for index in range(0, len(pieces), 2)
               if re.match(r"^(?:remind me\b|set\s+(?:a\s+)?timer\b)", _POLITE.sub("", pieces[index].strip()), re.I)
               and reminder_plan(_POLITE.sub("", pieces[index].strip()))[1]]
    if len(invalid) != 1:
        return "", WORKFLOW_QUESTION
    index = invalid[0]
    clause = _POLITE.sub("", pieces[index].strip())
    delay = re.sub(r"^(?:in|after|for)\s+", "", message, flags=re.I)
    body = re.sub(r"^remind me\s*", "", clause, flags=re.I)
    implicit = re.match(r"^(?:(?:(?:to\s+(?:do\s+)?|about\s+)?(?:it|this|that))\b|in\b|at\b|tomorrow\b|today\b|tonight\b)", body, re.I)
    if clause.lower().startswith("remind me") and (not body or implicit):
        pieces[index] = f"remind me in {delay}"
    else:
        resumed = reminder_followup(message, [{"role": "user", "content": clause},
                                             {"role": "assistant", "content": TIME_QUESTION}])
        if not resumed or resumed[1]:
            return "", WORKFLOW_QUESTION
        pieces[index] = resumed[0]
    return " ".join(piece.strip() for piece in pieces), ""


def workflow_plan(message):
    # Import locally: intent routing imports this planner before TaskManager loads.
    from tasks_service import parse_task_payload
    text = _WORKFLOW.sub("", _POLITE.sub("", message.strip()), count=1)
    pieces = _SEPARATOR.split(text)
    if len(pieces) < 3:
        return None, WORKFLOW_QUESTION
    steps, previous, latest_task, latest_reminder = [], None, None, None
    for index in range(0, len(pieces), 2):
        clause = _POLITE.sub("", pieces[index].strip().rstrip(".!"))
        connector = pieces[index - 1].lower() if index else ""
        key = f"step{len(steps) + 1}"
        depends = [previous] if previous else []
        task = _TASK.match(clause)
        # 'then' following a reminder means after its deadline, not after creation.
        if latest_reminder and connector in {"then", "and then"} and (task or re.match(r"^(?:notify|tell)\s+me\s+", clause, re.I)):
            wait_key = f"step{len(steps) + 1}"
            steps.append({"id": wait_key, "action": "wait_for_reminder", "depends_on": list(dict.fromkeys(depends + [latest_reminder])),
                          "inputs": {"reminder_step_id": latest_reminder, "until": "due"}})
            key, depends = f"step{len(steps) + 1}", [wait_key]
        if task:
            try:
                payload = parse_task_payload(clause[task.end():])
                if not payload["title"]:
                    return None, WORKFLOW_QUESTION
                inputs = TaskInputs(**payload).model_dump(mode="json")
            except (ValueError, OverflowError):
                return None, "What valid title and due date should the workflow task use?"
            steps.append({"id": key, "action": "create_task", "depends_on": depends, "inputs": inputs})
            latest_task = key
        elif re.match(r"^(?:remind\s+me\b|set\s+(?:a\s+)?timer\b)", clause, re.I):
            if latest_task and re.match(r"^remind me\s+(?:(?:to\s+(?:do\s+)?(?:it|this|that)|about\s+(?:it|this|that))\s+)?in\b", clause, re.I):
                title = next(step["inputs"]["title"] for step in steps if step["id"] == latest_task)
                clause = re.sub(r"^remind me\s+.*?\bin\s+", f"remind me to {title} in ", clause, count=1, flags=re.I)
            plan, question = reminder_plan(clause)
            if question:
                return None, WORKFLOW_TIME_QUESTION
            inputs = dict(plan["inputs"])
            if latest_task:
                # Link only an exact label or an explicit pronoun, never an unrelated activity.
                title = next(step["inputs"]["title"] for step in steps if step["id"] == latest_task)
                if inputs["label"].casefold() == title.casefold():
                    inputs["task_step_id"] = latest_task
                    if latest_task not in depends:
                        depends.append(latest_task)
            steps.append({"id": key, "action": "create_reminder", "depends_on": depends, "inputs": inputs})
            latest_reminder = key
        elif re.match(r"^(?:notify|tell)\s+me\s+", clause, re.I):
            message_text = re.sub(r"^(?:notify|tell)\s+me\s+(?:that\s+)?", "", clause, flags=re.I)
            steps.append({"id": key, "action": "notify", "depends_on": depends, "inputs": {"message": message_text}})
        else:
            return None, WORKFLOW_QUESTION
        previous = key
    # A linked reminder tracks task completion, not merely successful creation.
    linked = next((step for step in reversed(steps) if step["action"] == "create_reminder" and step["inputs"].get("task_step_id")), None)
    if linked:
        steps.append({"id": f"step{len(steps) + 1}", "action": "wait_for_reminder", "depends_on": list(dict.fromkeys([previous, linked["id"]])),
                      "inputs": {"reminder_step_id": linked["id"], "until": "completed"}})
    try:
        title = next((step["inputs"]["title"] for step in steps if step["action"] == "create_task"),
                     next((step["inputs"]["label"] for step in steps if step["action"] == "create_reminder"), "Workflow"))
        return WorkflowPlan(title=title, steps=steps), ""
    except ValueError:
        return None, WORKFLOW_QUESTION
