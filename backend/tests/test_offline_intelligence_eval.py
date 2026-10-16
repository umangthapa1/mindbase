"""Offline, corpus-style evaluation for Mindbase intelligence boundaries.

This file deliberately exercises the deterministic seams below the chat endpoint:

* ``route_message`` for tool selection and contextual clarification;
* ``ChatIntelligence.detect_intent`` for prompt-mode selection;
* ``reminder_plan`` and ``workflow_plan`` for validated plans; and
* Pydantic workflow validation for graph and input safety.

No FastAPI client, database, memory store, mail service, Ollama call, or network
connection is needed. The small evaluator reports passed/total cases per concern
so a new corpus entry is a measurable regression check rather than an example
that can silently stop running.
"""

from dataclasses import dataclass
import socket
from typing import Callable, Iterable

import pytest
from pydantic import ValidationError

from intelligence import ChatIntelligence
from intent_routing import (
    TASK_DETAILS_QUESTION,
    TASK_OR_MAIL_QUESTION,
    route_message,
)
from ollama import ollama_client
from workflow_planner import (
    WORKFLOW_QUESTION,
    WORKFLOW_TIME_QUESTION,
    WorkflowPlan,
    workflow_plan,
)
from workspace_planner import (
    BOUNDS_QUESTION,
    REMINDER_QUESTION,
    TIME_QUESTION,
    reminder_plan,
)


@pytest.fixture(autouse=True)
def _block_external_services(monkeypatch):
    """Make accidental Ollama/network use fail this test module immediately."""

    def blocked_connect(*_args, **_kwargs):
        raise AssertionError("offline intelligence evaluation attempted network access")

    async def blocked_ollama_call(*_args, **_kwargs):
        raise AssertionError("offline intelligence evaluation attempted an Ollama call")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    for method in (
        "check_health",
        "generate",
        "generate_embedding",
        "get_model",
        "list_models",
        "pull_model",
        "set_model",
        "stream_generate",
    ):
        monkeypatch.setattr(ollama_client, method, blocked_ollama_call)


@dataclass(frozen=True)
class EvaluationMetric:
    category: str
    total: int
    passed: int
    failures: tuple[str, ...]


def _evaluate_cases(
    category: str,
    cases: Iterable[object],
    check: Callable[[object], None],
) -> EvaluationMetric:
    failures = []
    total = 0
    for case in cases:
        total += 1
        name = getattr(case, "name", f"case-{total}")
        try:
            check(case)
        except Exception as exc:  # Report the full corpus in one test failure.
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    return EvaluationMetric(category, total, total - len(failures), tuple(failures))


def _assert_green(metric: EvaluationMetric) -> None:
    assert not metric.failures, (
        f"{metric.category}: {metric.passed}/{metric.total} cases passed\n"
        + "\n".join(metric.failures)
    )


def _history(*turns: tuple[str, str]) -> list[dict[str, str]]:
    return [{"role": role, "content": content} for role, content in turns]


@dataclass(frozen=True)
class RoutingCase:
    name: str
    message: str
    tool: str
    history: tuple[tuple[str, str], ...] = ()
    question: str = ""
    task_text: str | None = None


ROUTING_CASES = (
    RoutingCase(
        "explicit task wins over email noun",
        "Add task: reply to Alice's email",
        "add_task",
        task_text="reply to Alice's email",
    ),
    RoutingCase("future email activity is a task", "I need to email Alice", "add_task", task_text="email Alice"),
    RoutingCase("inbox listing", "Any new mail?", "check_mail"),
    RoutingCase("named reply lookup", "Did Alice reply?", "check_mail"),
    RoutingCase("relative timer", "Remind me to stretch in 15 minutes", "reminder"),
    RoutingCase(
        "multi-step request",
        "Create a task to call grandpa tomorrow and remind me in 30 minutes",
        "workflow",
    ),
    RoutingCase("explicit calendar event", "Add an event: team meeting tomorrow at 3pm", "schedule"),
    RoutingCase("named widget deletion", "Delete the Focus widget", "delete_widget"),
    RoutingCase(
        "grounded completion claim",
        "I pushed the code",
        "complete_task",
        history=(("assistant", "Created task: **Push the code**"),),
    ),
    RoutingCase("factual memory remains chat", "Remember that I prefer tea", "chat"),
    RoutingCase("coding question remains chat", "Write a Python function", "chat"),
    RoutingCase(
        "task-versus-mail ambiguity",
        "Email Alice",
        "clarify",
        question=TASK_OR_MAIL_QUESTION,
    ),
    RoutingCase("missing task details", "Add", "clarify", question=TASK_DETAILS_QUESTION),
)


def _check_routing(case: RoutingCase) -> None:
    route = route_message(case.message, _history(*case.history))
    assert route.tool == case.tool
    assert route.question == case.question
    if case.task_text is not None:
        assert route.task_text == case.task_text


@dataclass(frozen=True)
class IntentCase:
    name: str
    message: str
    intent: str


INTENT_CASES = (
    IntentCase("document summary", "Summarize my uploaded PDF", "document"),
    IntentCase("calendar view", "What's on my calendar this week?", "calendar"),
    IntentCase("planning focus", "What should I focus on today?", "planning"),
    IntentCase("Python implementation", "Write a Python function to parse dates", "coding"),
    IntentCase("research comparison", "Research the pros and cons of SQLite", "research"),
    IntentCase("unclassified factual question", "What is the capital of France?", "general"),
    IntentCase(
        "specific document/coding tie uses document",
        "Explain the code in my document",
        "document",
    ),
)


def _check_intent(case: IntentCase) -> None:
    assert ChatIntelligence().detect_intent(case.message) == case.intent


@dataclass(frozen=True)
class ClarificationCase:
    name: str
    message: str
    tool: str
    question: str
    history: tuple[tuple[str, str], ...] = ()
    task_text: str | None = None
    reminder_has_plan: bool = False


CLARIFICATION_CASES = (
    ClarificationCase("ambiguous mail command", "Email Alice", "clarify", TASK_OR_MAIL_QUESTION),
    ClarificationCase(
        "yes does not choose task or mail",
        "yes",
        "clarify",
        TASK_OR_MAIL_QUESTION,
        history=(
            ("user", "Email Alice"),
            ("assistant", TASK_OR_MAIL_QUESTION),
        ),
    ),
    ClarificationCase("bare task command", "Add task", "clarify", TASK_DETAILS_QUESTION),
    ClarificationCase("missing reminder details", "remind me", "reminder", REMINDER_QUESTION),
    ClarificationCase(
        "absolute reminder timing asks for relative timing",
        "remind me to call Alice tomorrow",
        "reminder",
        TIME_QUESTION,
    ),
    ClarificationCase(
        "workflow timing asks before execution",
        "Create a task to call Alice and remind me tomorrow",
        "workflow",
        WORKFLOW_TIME_QUESTION,
    ),
    ClarificationCase(
        "unsupported workflow step asks for a complete restatement",
        "Create a task to call Alice then email Bob",
        "workflow",
        WORKFLOW_QUESTION,
    ),
    ClarificationCase(
        "explicit task answer resumes original request",
        "add a task",
        "add_task",
        "",
        history=(
            ("user", "Email Alice"),
            ("assistant", TASK_OR_MAIL_QUESTION),
        ),
        task_text="Email Alice",
    ),
    ClarificationCase(
        "timing answer resumes original reminder",
        "in 30 seconds",
        "reminder",
        "",
        history=(
            ("user", "remind me to stretch tomorrow"),
            ("assistant", TIME_QUESTION),
        ),
        reminder_has_plan=True,
    ),
)


def _check_clarification(case: ClarificationCase) -> None:
    route = route_message(case.message, _history(*case.history))
    question = route.question

    if route.tool == "reminder":
        plan, question = reminder_plan(route.query)
        assert bool(plan["inputs"]) is case.reminder_has_plan
    elif route.tool == "workflow":
        plan, question = workflow_plan(route.query)
        assert plan is None

    assert route.tool == case.tool
    assert question == case.question
    if case.task_text is not None:
        assert route.task_text == case.task_text


@dataclass(frozen=True)
class ReminderCase:
    name: str
    message: str
    inputs: dict[str, object]
    question: str = ""


REMINDER_CASES = (
    ReminderCase(
        "minutes",
        "remind me to stretch in 15 minutes",
        {"label": "Stretch", "duration_seconds": 900},
    ),
    ReminderCase(
        "combined hours and minutes",
        "remind me to sleep in 1 hour and 30 minutes",
        {"label": "Sleep", "duration_seconds": 5400},
    ),
    ReminderCase("timer default label", "set a timer for 30 seconds", {"label": "Timer", "duration_seconds": 30}),
    ReminderCase("informal unit", "Please remind me to breathe in 3sec", {"label": "Breathe", "duration_seconds": 3}),
    ReminderCase(
        "timer with label",
        "start a timer for 1 minute to stretch",
        {"label": "Stretch", "duration_seconds": 60},
    ),
    ReminderCase("negative duration", "remind me to stretch in -3 seconds", {}, TIME_QUESTION),
    ReminderCase("zero duration", "remind me to stretch in 0 minutes", {}, BOUNDS_QUESTION),
    ReminderCase("fractional duration", "remind me to stretch in 1.5 hours", {}, TIME_QUESTION),
    ReminderCase("absolute date", "remind me to check mail tomorrow", {}, TIME_QUESTION),
    ReminderCase("recurring duration", "remind me to stretch every hour", {}, TIME_QUESTION),
    ReminderCase("over maximum duration", "remind me to stretch in 999999999 hours", {}, BOUNDS_QUESTION),
    ReminderCase("missing label and delay", "remind me", {}, REMINDER_QUESTION),
)


def _check_reminder(case: ReminderCase) -> None:
    plan, question = reminder_plan(case.message)
    assert question == case.question
    assert plan["intent"] == "create_reminder"
    assert plan["capability_id"] == "timer"
    assert plan["inputs"] == case.inputs
    assert plan["confidence"] == (1.0 if case.inputs else 0.0)


@dataclass(frozen=True)
class WorkflowCase:
    name: str
    message: str
    title: str
    actions: tuple[str, ...]
    dependencies: tuple[tuple[str, ...], ...]
    reminder: tuple[str, int] | None = None
    notification: str | None = None


WORKFLOW_CASES = (
    WorkflowCase(
        "task and linked reminder",
        "Create a task to call grandpa tomorrow and remind me in 30 minutes",
        "Call grandpa",
        ("create_task", "create_reminder", "wait_for_reminder"),
        ((), ("step1",), ("step2",)),
        reminder=("Call grandpa", 1800),
    ),
    WorkflowCase(
        "reminder then due notification",
        "workflow: remind me to stretch in 3 seconds then notify me that stretching is due",
        "Stretch",
        ("create_reminder", "wait_for_reminder", "notify"),
        ((), ("step1",), ("step2",)),
        reminder=("Stretch", 3),
        notification="stretching is due",
    ),
    WorkflowCase(
        "task then notification",
        "workflow: create task: Buy milk and notify me that it is due",
        "Buy milk",
        ("create_task", "notify"),
        ((), ("step1",)),
        notification="it is due",
    ),
    WorkflowCase(
        "task reminder notification chain",
        "workflow: add task: buy milk and remind me to do it in 30 seconds and notify me that it is due",
        "Buy milk",
        ("create_task", "create_reminder", "notify", "wait_for_reminder"),
        ((), ("step1",), ("step2",), ("step3", "step2")),
        reminder=("Buy milk", 30),
        notification="it is due",
    ),
)


def _check_workflow(case: WorkflowCase) -> None:
    plan, question = workflow_plan(case.message)
    assert question == ""
    assert isinstance(plan, WorkflowPlan)
    assert plan.title == case.title
    assert tuple(step.action for step in plan.steps) == case.actions
    assert tuple(tuple(step.depends_on) for step in plan.steps) == case.dependencies
    assert [step.id for step in plan.steps] == [f"step{i}" for i in range(1, len(plan.steps) + 1)]

    if case.reminder:
        reminder = next(step for step in plan.steps if step.action == "create_reminder")
        inputs = reminder.inputs.model_dump()
        assert (inputs["label"], inputs["duration_seconds"]) == case.reminder
        if inputs.get("task_step_id"):
            assert inputs["task_step_id"] in reminder.depends_on

    if case.notification:
        notification = next(step for step in plan.steps if step.action == "notify")
        assert notification.inputs.message == case.notification


@dataclass(frozen=True)
class InvalidWorkflowCase:
    name: str
    message: str
    question: str


INVALID_WORKFLOW_CASES = (
    InvalidWorkflowCase(
        "missing relative delay",
        "Create a task to call Alice and remind me tomorrow",
        WORKFLOW_TIME_QUESTION,
    ),
    InvalidWorkflowCase(
        "unsupported email step",
        "Create a task to call Alice then email Bob",
        WORKFLOW_QUESTION,
    ),
    InvalidWorkflowCase(
        "negative relative delay",
        "workflow: create task: Buy milk and remind me in -3 seconds",
        WORKFLOW_TIME_QUESTION,
    ),
    InvalidWorkflowCase("no workflow steps", "workflow", WORKFLOW_QUESTION),
)


def _check_invalid_workflow(case: InvalidWorkflowCase) -> None:
    plan, question = workflow_plan(case.message)
    assert plan is None
    assert question == case.question


def _linked_plan_payload() -> dict:
    return {
        "title": "Call grandpa",
        "steps": [
            {"id": "task", "action": "create_task", "inputs": {"title": "Call grandpa"}},
            {
                "id": "reminder",
                "action": "create_reminder",
                "depends_on": ["task"],
                "inputs": {
                    "label": "Call grandpa",
                    "duration_seconds": 30,
                    "task_step_id": "task",
                },
            },
            {
                "id": "done",
                "action": "wait_for_reminder",
                "depends_on": ["reminder"],
                "inputs": {"reminder_step_id": "reminder", "until": "completed"},
            },
        ],
    }


def _unknown_action(payload: dict) -> None:
    payload["steps"][0]["action"] = "execute_python"


def _forward_dependency(payload: dict) -> None:
    payload["steps"][0]["depends_on"] = ["reminder"]


def _wrong_link(payload: dict) -> None:
    payload["steps"][2]["inputs"]["reminder_step_id"] = "task"


def _duplicate_id(payload: dict) -> None:
    payload["steps"][1]["id"] = "task"


def _extra_code(payload: dict) -> None:
    payload["steps"][0]["inputs"]["code"] = "delete_all()"


def _zero_delay(payload: dict) -> None:
    payload["steps"][1]["inputs"]["duration_seconds"] = 0


SCHEMA_SAFETY_CASES = (
    ("unknown action", _unknown_action),
    ("forward dependency", _forward_dependency),
    ("wrong linked reference", _wrong_link),
    ("duplicate step ID", _duplicate_id),
    ("extra executable field", _extra_code),
    ("non-positive reminder", _zero_delay),
)


@dataclass(frozen=True)
class SafetyCase:
    name: str
    message: str
    tool: str
    history: tuple[tuple[str, str], ...] = ()
    planner_question: str | None = None


SAFETY_CASES = (
    SafetyCase("negated task", "Do not add a task", "chat"),
    SafetyCase("cancellation", "cancel", "chat"),
    SafetyCase("memory wording", "Remember to email Alice", "chat"),
    SafetyCase("ambiguous activity", "Email Alice", "clarify"),
    SafetyCase(
        "unclear clarification answer",
        "yes",
        "clarify",
        history=(("user", "Email Alice"), ("assistant", TASK_OR_MAIL_QUESTION)),
    ),
    SafetyCase(
        "absolute reminder cannot execute",
        "remind me to call Alice tomorrow",
        "reminder",
        planner_question=TIME_QUESTION,
    ),
    SafetyCase(
        "unsupported workflow cannot execute a subset",
        "Create a task to call Alice then email Bob",
        "workflow",
        planner_question=WORKFLOW_QUESTION,
    ),
    SafetyCase(
        "invalid workflow timing cannot execute a subset",
        "workflow: create task: Buy milk and remind me in -3 seconds",
        "workflow",
        planner_question=WORKFLOW_TIME_QUESTION,
    ),
)


def _check_safety(case: SafetyCase) -> None:
    route = route_message(case.message, _history(*case.history))
    assert route.tool == case.tool
    if case.tool in {"chat", "clarify"}:
        assert route.tool not in {"add_task", "complete_task", "reminder", "workflow", "schedule"}
    if case.planner_question is not None and route.tool == "reminder":
        plan, question = reminder_plan(route.query)
        assert plan["inputs"] == {}
        assert question == case.planner_question
    if case.planner_question is not None and route.tool == "workflow":
        plan, question = workflow_plan(route.query)
        assert plan is None
        assert question == case.planner_question


def test_offline_routing_corpus_is_correct():
    _assert_green(_evaluate_cases("routing", ROUTING_CASES, _check_routing))


def test_offline_intent_corpus_is_correct():
    _assert_green(_evaluate_cases("intelligence intent", INTENT_CASES, _check_intent))


def test_offline_clarification_corpus_is_correct():
    _assert_green(_evaluate_cases("clarification", CLARIFICATION_CASES, _check_clarification))


def test_offline_reminder_planning_corpus_is_correct():
    _assert_green(_evaluate_cases("reminder planning", REMINDER_CASES, _check_reminder))


def test_offline_workflow_planning_corpus_is_correct():
    _assert_green(_evaluate_cases("workflow planning", WORKFLOW_CASES, _check_workflow))
    _assert_green(_evaluate_cases("workflow rejection", INVALID_WORKFLOW_CASES, _check_invalid_workflow))


def test_offline_safety_corpus_is_correct():
    _assert_green(_evaluate_cases("safety boundaries", SAFETY_CASES, _check_safety))


@pytest.mark.parametrize("name,mutate", SCHEMA_SAFETY_CASES, ids=[case[0] for case in SCHEMA_SAFETY_CASES])
def test_workflow_schema_rejects_unsafe_graphs(name: str, mutate: Callable[[dict], None]):
    payload = _linked_plan_payload()
    mutate(payload)
    with pytest.raises(ValidationError):
        WorkflowPlan(**payload)
