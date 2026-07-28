import re

# Copy the exact patterns from the file
_EMAIL_PATTERNS = [
    # Original patterns kept for backward compatibility
    r'(check|show|get|read|fetch|list|look at|see|find|search|open|summari[sz]e|reply|respond|draft).{0,40}(email|gmail|mail|inbox|message)',
    r'(email|gmail|mail|inbox|message).{0,40}(check|show|get|read|fetch|list|recent|latest|new|unread|from)',
    r'(any|do i have|got any|have any|are there|were there).{0,30}(email|mail|message)',
    r'(what|which).{0,30}(email|mail|message|inbox)',
    r'(unread|unopened).{0,30}(email|mail|message)',
    r'(email|mail|message).{0,20}(unread|unopened|new|from)',
    r'emails?.{0,40}from',
    r'from.{0,40}emails?',
    r'\binbox\b',
    r'\bgmail\b',
    
    # ENHANCED PATTERNS for natural language understanding
    # Phrases that start with exploratory language
    r'(tell\s+me\s+about|describe|what.?s?\s+the?\s+status\s+of|how\s+many|show\s+me\s+what.?s?\s+in|look\s+at\s+my|see\s+if\s+I\s+have|did\s+I\s+get|have\s+I\s+received|any\s+(new\s+)?|are\s+there\s+|what\s+emails\s+do\s+I\s+have|do\s+I\s+have\s+any\s+email|got\s+any\s+email|no\s+new\s+email)\b.*\b(email|emails?|mail|messages?|inbox|gmail)\b',
    
    # Phrases that end with exploratory language
    r'\b(email|emails?|mail|messages?|inbox|gmail).*\b(tell\s+me\s+about|describe|what.?s?\s+the?\s+status\s+of|how\s+many|show\s+me\s+what.?s?\s+in|look\s+at\s+my|see\s+if\s+I\s+have|did\s+I\s+get|have\s+I\s+received|any\s+(new\s+)?|are\s+there\s+|what\s+emails\s+do\s+I\s+have|do\s+I\s+have\s+any\s+email|got\s+any\s+email|no\s+new\s+email)\b',
    
    # Time-based email queries (more flexible)
    r'\b(latest|recent|today.?s?|yesterday.?s?|this\s+morning.?s?|this\s+afternoon.?s?|this\s+evening.?s?|this\s+week.?s?|unread\s+|new\s+|pending\s+|important\s+|urgent\s+)\b.*\b(email|emails?|mail|messages?|inbox|gmail)\b',
    r'\b(email|emails?|mail|messages?|inbox|gmail).*\b(latest|recent|today.?s?|yesterday.?s?|this\s+morning.?s?|this\s+afternoon.?s?|this\s+evening.?s?|this\s+week.?s?|unread\s+|new\s+|pending\s+|important\s+|urgent\s+)\b',
    
    # Sender-focused queries
    r'\b(from\s+|sender\s+|who\s+is\s+from\s+|messages\s+from\s+|email\s+from\s+|received\s+from\s+|got\s+email\s+from)\b.*\b([a-zA-Z0-9._%+\-@]+)',
    r'\b([a-zA-Z0-9._%+\-@]+).*\b(from\s+|sender\s+|who\s+is\s+from\s+|messages\s+from\s+|email\s+from\s+|received\s+from\s+|got\s+email\s+from)\b',
    
    # Content/topic-focused queries
    r'\b(about\s+|regarding\s+|concerning\s+|topic\s+|subject\s+|regarding\s+|re:)\s*.*?\b(email|emails?|mail|messages?|inbox|gmail)\b',
    r'\b(email|emails?|mail|messages?|inbox|gmail).*\b(about\s+|regarding\s+|concerning\s+|topic\s+|subject\s+|regarding\s+|re:)\s*.*?\b',
    
    # Action-oriented email requests
    r'\b(read\s+the\s+|open\s+the\s+|check\s+the\s+|look\s+at\s+the\s+|see\s+the\s+|what.?s?\s+in\s+the\s+|content\s+of\s+|meaning\s+of\s+meaning\s+of\s+|meaning\s+of\s+)\s+(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+)?\s*(email|message|mail)\b',
    r'\b(email|message|mail)\s+(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+)?\s*(read\s+the\s+|open\s+the\s+|check\s+the\s+|look\s+at\s+the\s+|see\s+the\s+|what.?s?\s+in\s+the\s+|content\s+of\s+|meaning\s+of\s+|meaning\s+of\s+)\b',
    
    # Summary requests
    r'\b(summarize\s+|summary\s+of\s+|give\s+me\s+a\s+summary\s+of\s+|brief\s+me\s+on\s+|quick\s+overview\s+of\s+|summarize\s+this\s+|summarize\s+the\s+)(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+)?\s*(email|message|mail)\b',
    r'\b(email|message|mail)\s+(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+)?\s*(summarize\s+|summary\s+of\s+|give\s+me\s+a\s+summary\s+of\s+|brief\s+me\s+on\s+|quick\s+overview\s+of\s+|summarize\s+this\s+|summarize\s+the\s+)\b',
]

_EMAIL_FOLLOWUP = re.compile(
    r'\b(summari[sz]e|summary|reply|respond|draft|forward)\b'
    r'|\b(read|open)\s+(the|that|this|it|first|second|third|last|latest)\b'
    # "the one", "the google one", "that email", "the leetcode message", "first one"…
    r'|\b(the|that|this|first|second|third|fourth|last|latest)\s+(?:[a-z0-9]+\s+)?(one|email|message|mail)\b'
    r'|\bfrom\s+[a-z0-9._%+\-@]+'
    # Enhanced follow-up patterns
    r'|\b(what\s+did\s+it\s+say|what\s+does\s+it\s+say|content\s+of|meaning\s+of|read\s+the\s+|open\s+the\s+|tell\s+me\s+about\s+|describe\s+|what.?s?\s+in\s+)\s+(the|that|this|it|first|second|third|last|latest|one|null)\s*(email|message|mail)\b'
    r'|\b(summarize\s+|summary\s+of\s+|give\s+me\s+a\s+summary\s+of\s+|brief\s+me\s+on\s+|quick\s+overview\s+of\s+)\s+(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+|one\s+|null\s*)\s*(email|message|mail)\b'
    r'|\b(the\s+|that\s+|this\s+|it\s+|first\s+|second\s+|third\s+|last\s+|latest\s+|one\s+|null\s*)\s*(email|message|mail)\s*(summarize\s+|summary\s+of\s+|give\s+me\s+a\s+summary\s+of\s+|brief\s+me\s+on\s+|quick\s+overview\s+of\s+|what\s+did\s+it\s+say|what\s+does\s+it\s+say|content\s+of|meaning\s+of|read\s+the\s+|open\s+the\s+|tell\s+me\s+about\s+|describe\s+|what.?s?\s+in\s+)\b',
    re.I,
)

def _history_shows_emails(history) -> bool:
    """True if the conversation is in 'email mode' — a recent USER turn asked about
    email (deterministic, pattern-based), or an assistant turn listed emails. Used so
    short follow-ups like 'summarize the one from leetcode' resolve to email context."""
    if not history:
        return False
    for msg in reversed(history[-6:]):
        role = msg.get("role")
        text = msg.get("content") or ""
        if role == "user":
            m = text.lower()
            if any(re.search(p, m) for p in _EMAIL_PATTERNS):
                return True
        elif role == "assistant":
            if "Subject:" in text and ("From:" in text or "Received:" in text):
                return True
    return False

def _is_email_query(message: str, history=None) -> bool:
    msg = message.lower()
    if any(re.search(p, msg) for p in _EMAIL_PATTERNS):
        return True
    # A short follow-up referencing emails that were just shown.
    if _history_shows_emails(history) and _EMAIL_FOLLOWUP.search(msg):
        return True
    return False

# Test cases
test_cases = [
    "tell me about my latest emails",
    "show me my emails from instagram",
    "what emails do I have from work",
    "check my mail",
    "look at my messages",
    "do i have any emails today",
    "any new email from john",
    "summarize the latest email from instagram",
    "give me a summary of this email",
    "show me what is in my inbox"
]

print("Testing _is_email_query function:")
print("=" * 50)
for case in test_cases:
    result = _is_email_query(case)
    print(f'"{case}" -> {"EMAIL" if result else "NOT EMAIL"}')

print("\n" + "=" * 50)
print("Testing follow-up detection:")
# Simulate history showing emails
history_with_emails = [
    {"role": "assistant", "content": "Here are the matching emails from your local inbox:\n\n1. From: Test Sender <test@example.com>\n   Subject: Test Email\n   Received: Jul 28, 03:18 PM\n   Preview: This is a test email..."}
]

followup_cases = [
    "summarize the first email",
    "tell me about the one from test",
    "what does it say",
    "open the second email"
]

for case in followup_cases:
    result = _is_email_query(case, history_with_emails)
    print(f'"{case}" -> {"FOLLOW-UP EMAIL" if result else "NOT EMAIL FOLLOW-UP"}')
