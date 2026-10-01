"""Deterministic tool selection; explicit requests outrank words in their payload.

The app implements add_task with TaskManager and check_mail with the local inbox
query. These are routing labels, not additional LLM/network tools. Unclear mail
vs. task commands ask one question before either tool runs.
"""
from dataclasses import dataclass
import re
from typing import Literal

TOOL_DESCRIPTIONS = {
    "add_task": "Create a to-do/reminder for a requested future action; do NOT use for questions about existing mail or inbox contents.",
    "complete_task": "Complete the single task just discussed; do NOT use for negations, future plans, or ambiguous task references.",
    "check_mail": "Look up existing emails, messages or replies in the synced inbox; do NOT use when the user wants a task reminding them to handle mail.",
}
ROUTING_EXAMPLES = (
    ("Remind me to check my email tomorrow", "add_task"),
    ("Add reply to Alice's email to my tasks", "add_task"),
    ("I need to email Alice", "add_task"),
    ("Any new mail?", "check_mail"),
    ("Did Alice reply?", "check_mail"),
    ("Email Alice", "clarify"),
)
TASK_OR_MAIL_QUESTION = "Do you want me to add a task or check your email?"
TASK_DETAILS_QUESTION = "What would you like me to add as a task?"


@dataclass(frozen=True)
class ToolRoute:
    tool: Literal["add_task", "complete_task", "check_mail", "schedule", "chat", "clarify"]
    query: str
    task_text: str = ""
    question: str = ""


_POLITE = re.compile(r"^(?:(?:please|(?:can|could|would|will)\s+(?:you|u))\s+)+", re.I)
_ACK_PREFIX = re.compile(r"^(?:(?:yes|yeah|yep|yup|okay|ok)[,!.]?\s+)+", re.I)
_COMPLETED_VERBS = {
    "pushed": "push", "uploaded": "upload", "sent": "send", "emailed": "email",
    "replied": "reply", "called": "call", "paid": "pay", "submitted": "submit",
    "finished": "finish", "completed": "complete", "fixed": "fix", "reviewed": "review",
    "bought": "buy", "wrote": "write", "booked": "book", "cleaned": "clean",
}
_UNCLEAR_CHOICE = re.compile(r"(?:yes|yeah|sure|ok(?:ay)?|do it|go ahead|either|maybe|not sure)[.!?]*", re.I)
_MAIL_WORD = re.compile(r"\b(emails?|e-mails?|mail|inbox|gmail|messages?|replies|reply)\b", re.I)
_REPLY_QUESTION = re.compile(
    r"^(?:(?:check|see)\s+(?:if|whether)\s+|(?:did|has|have)\s+)"
    r"(?P<sender>.+?)\s+(?:reply|replied|respond|responded)\b", re.I,
)
_TASK_PREFIX = re.compile(
    r"^(?:(?:add|create)\s+(?:a\s+)?(?:new\s+)?(?:task|todo|to-do|reminder)(?:\s+(?:to|for))?"
    r"|new\s+task|task|todo|to-do|remind me to|i need to|i have to"
    r"|note(?:\s+(?:down|to self))?\s+to)\s*[:\s]\s*(.+)$", re.I,
)
_CALENDAR_COMMAND = re.compile(
    r"^(?:(?:add|create|schedule|book)\s+(?:an?\s+)?(?:event|meeting|appointment)\b"
    r"|(?:add|create|put|move|reschedule|cancel|delete|remove)\b.*\b(?:calendar|calender|event|meeting|appointment)\b"
    r"|(?:calendar|calender)\s*:)", re.I,
)


def completion_claim(message: str) -> str | None:
    """Return '' for 'done/it is done', a normalized activity, or None.

    Only positive first-person completion statements are accepted, never a
    question, a negation, or a promise to do something later. The task service
    must still resolve one explicit recent task and verify an activity matches.
    """
    text = _ACK_PREFIX.sub("", message.strip()).lower().replace("’", "'")
    text = re.sub(r"[,!.\s]+(?:thanks|thank you)[.!]*$", "", text)
    if "?" in text or re.search(r"\b(not|never|haven't|didn't|isn't|won't|can't|will|would|could|should|might|maybe|if)\b", text):
        return None
    if re.fullmatch(
        r"(?:(?:(?:i(?:'m| am)|it(?:'s| is))\s+)?(?:done|finished|completed|complete)"
        r"|i(?:'ve| have)?\s+(?:just\s+|already\s+)?(?:did|done|finished|completed)\s+(?:it|that|this|the task)"
        r"|(?:mark\s+)?(?:that|this|it|the)(?:\s+(?:task|one))?\s+"
        r"(?:is\s+|as\s+|is\s+now\s+|now\s+|marked\s+|has\s+been\s+)?(?:complete|completed|done|finished))"
        r"[.!]*", text,
    ):
        return ""
    match = re.fullmatch(
        r"i(?:'ve| have)?\s+(?:just\s+|already\s+)?(" + "|".join(_COMPLETED_VERBS) + r")\s+(.+?)[.!]*", text,
    )
    if match:
        return f"{_COMPLETED_VERBS[match.group(1)]} {match.group(2)}"
    return None


def is_reply_query(message: str) -> bool:
    return bool(_REPLY_QUESTION.search(_POLITE.sub("", message.strip())))


def reply_sender(message: str) -> str | None:
    match = _REPLY_QUESTION.search(_POLITE.sub("", message.strip()))
    if match:
        sender = match.group("sender").strip().rstrip("?!.,")
        if sender.lower() not in {"anyone", "someone", "they", "he", "she"}:
            return sender
    return None


def _mail_lookup(text: str) -> bool:
    if _REPLY_QUESTION.search(text):
        return True
    return bool(_MAIL_WORD.search(text) and (
        re.match(r"^(?:check|show|list|read|open|fetch|find|search|look|see|get|got|received|any|did|has|have|do i|are there|is there|what|which|who|how many|tell me|give me|brief me|describe|content of|meaning of|summary of|explain|summari[sz]e|draft|respond)\b", text, re.I)
        or re.search(r"\b(?:from|unread|new|latest|recent|about|regarding)\b", text, re.I)
        or re.fullmatch(r"(?:my\s+)?(?:inbox|gmail|replies)[?!.]*", text, re.I)
    ))


def _recent_mail_context(history) -> bool:
    for turn in reversed((history or [])[-6:]):
        text = turn.get("content", "")
        if turn.get("role") == "assistant":
            if re.match(r"^(?:Created task:|Added to calendar:|Completed task:|Deleted task:)", text):
                return False
            if "Subject:" in text and "From:" in text:
                return True
        if turn.get("role") == "user":
            text = _POLITE.sub("", text.strip())
            if _TASK_PREFIX.match(text) or _CALENDAR_COMMAND.match(text):
                return False
            if _mail_lookup(text):
                return True
    return False


def route_message(message: str, history=None) -> ToolRoute:
    """Choose a tool once, before a model or mutation; never infer permission from keywords alone."""
    history = history or []  # Previous turns only, excluding this user message.
    text = _POLITE.sub("", message.strip())
    lower = text.lower()

    # Cancellation/negation is not permission, including during clarification.
    if re.match(r"^(?:don't|do not|never|no thanks|never mind|nevermind|forget it)\b", lower) or re.fullmatch(r"(?:no|cancel)[.!?]*", lower):
        return ToolRoute("chat", message)

    # Resolve the answer to our own question without losing the original request.
    if history and history[-1].get("role") == "assistant":
        question = history[-1].get("content", "").strip()
        previous = next((m.get("content", "") for m in reversed(history[:-1])
                         if m.get("role") == "user" and not _UNCLEAR_CHOICE.fullmatch(m.get("content", "").strip())), "")
        if question == TASK_OR_MAIL_QUESTION and previous:
            if re.fullmatch(r"(?:add\s+)?(?:a\s+)?(?:task|reminder|todo)[.!]?", lower):
                return ToolRoute("add_task", previous, task_text=previous)
            if re.fullmatch(r"(?:check\s+)?(?:my\s+)?(?:mail|email|emails|inbox)[.!]?", lower):
                target = re.sub(r"^(?:email|mail|message|reply to|check)\s+", "", previous, flags=re.I).strip("?!.")
                return ToolRoute("check_mail", f"emails from {target}")
            if _UNCLEAR_CHOICE.fullmatch(text):
                return ToolRoute("clarify", message, question=TASK_OR_MAIL_QUESTION)
        if question == TASK_DETAILS_QUESTION and text and not _TASK_PREFIX.match(text):
            if _UNCLEAR_CHOICE.fullmatch(text):
                return ToolRoute("clarify", message, question=TASK_DETAILS_QUESTION)
            return ToolRoute("add_task", text, task_text=text)

    # Preserve factual memories and avoid acting on negated or explanatory commands.
    if re.match(r"^(?:remember|save this|store this|note that|keep in mind|fyi|memorize|add this to memory)\b", lower):
        return ToolRoute("chat", message)
    if re.match(r"^(?:how|why|what is|what does|write|implement|debug|explain)\b", lower) and re.search(r"\b(code|function|script|regex|error|program|api|works?)\b", lower):
        return ToolRoute("chat", message)
    if re.match(r"^(?:what (?:is|are)|how (?:does|do)|explain (?:how|what))\b", lower) and not re.search(r"\b(my|our|inbox|from|unread|latest)\b", lower):
        return ToolRoute("chat", message)

    # An explicit to-do wrapper wins even when the task contains 'email' or 'meeting'.
    task = _TASK_PREFIX.match(text)
    if task:
        return ToolRoute("add_task", message, task_text=task.group(1).strip())
    if _CALENDAR_COMMAND.search(text):
        return ToolRoute("schedule", text)
    if lower.strip(" :.!?") in {"add", "add a task", "add task", "create task", "new task", "task", "todo", "remind me", "schedule", "note to"}:
        return ToolRoute("clarify", message, question=TASK_DETAILS_QUESTION)
    if re.match(r"^(?:add|schedule)\s+", lower) and not re.search(r"\b(memory|note|document)\b", lower):
        body = re.sub(r"^(?:add|schedule)\s+", "", text, flags=re.I)
        body = re.sub(r"\s+to\s+(?:my\s+)?(?:tasks|to-do list|todo list)\s*$", "", body, flags=re.I)
        return ToolRoute("add_task", message, task_text=body)

    # Complete acknowledgements locally, including tasks whose titles mention
    # email. A past-tense activity needs task context; a bare 'done' can ask which.
    claim = completion_claim(text)
    task_context = any(m.get("role") == "assistant" and re.search(r"\btasks?\b", m.get("content", ""), re.I) for m in history[-6:])
    if claim is not None and (claim == "" or task_context):
        return ToolRoute("complete_task", text)
    # Do not feed 'yep, not done' or 'yep, I will ...' into the action model.
    acknowledged = _ACK_PREFIX.sub("", text)
    if acknowledged != text and re.match(r"^(?:i\b|not\b|it\b|that\b)", acknowledged, re.I):
        return ToolRoute("chat", message)
    if re.match(r"^(?:i\b|it\b|that\b|this\b)", acknowledged, re.I) and re.search(r"\b(?:not|isn't|haven't|didn't|will|going to)\b", acknowledged, re.I):
        return ToolRoute("chat", message)

    # Explicit task updates also outrank mail words in the target's title.
    if re.match(r"^(?:mark|set|change|update)\b", lower) and re.search(r"\b(?:priority|status|as (?:done|complete|completed|pending|in progress))\b", lower):
        return ToolRoute("schedule", text)
    if re.match(r"^(?:delete|remove|complete|finish|reschedule|move|start|begin)\b", lower) and re.search(r"\btask\b", lower):
        return ToolRoute("schedule", text)
    # A named task/calendar lookup isn't the ambiguous bare "check Alice".
    if re.match(r"^(?:(?:check|show|list|get)(?: me)?\s+|(?:what|which|any|do i have)\s+)(?:(?:my|the|all|pending|completed|open|upcoming)\s+)*(?:tasks?|todos?|calendar|calender|events?|agenda|schedule)\b", lower):
        return ToolRoute("chat", text)
    if _mail_lookup(text):
        return ToolRoute("check_mail", text)
    if re.match(r"^(?:summari[sz]e|explain|read)\b", lower) and re.search(r"\b(code|function|script|document|pdf|note|tasks?|calendar)\b", lower) and not _MAIL_WORD.search(text):
        return ToolRoute("chat", message)
    if _recent_mail_context(history) and re.search(
        r"^(?:or|and|what about|from|summari[sz]e|summary|draft|reply|respond|forward|read|open|what did it say|what does it say)\b|\b(?:the|that|this|first|second|third|last|latest)\s+(?:\w+\s+)?(?:one|email|message)\b", lower,
    ):
        return ToolRoute("check_mail", text)
    if _MAIL_WORD.search(text) or re.match(r"^(?:reply|respond|check)\b", lower):
        return ToolRoute("clarify", message, question=TASK_OR_MAIL_QUESTION)

    # Keep existing calendar/task update and contextual follow-up capabilities.
    if re.match(r"^(?:mark|complete|finish|finished|completed|done|start|begin|set|change|update|reschedule|move|delete|remove|cancel|book)\b", lower):
        return ToolRoute("schedule", text)
    schedule_history = any(re.search(r"\b(task|calendar|event|meeting|due)\b", m.get("content", ""), re.I) for m in history[-6:])
    if schedule_history and re.search(r"^(?:yes|yeah|yep|confirm|do it|go ahead|that|this|it|actually|instead|tomorrow|today|on|at)\b|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", lower):
        return ToolRoute("schedule", text)
    return ToolRoute("chat", message)
