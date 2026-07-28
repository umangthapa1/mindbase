import re

def _extract_email_search_terms(message: str) -> dict:
    '''Pull out useful filters from the natural language query.'''
    msg = message.lower()
    result = {'sender': None, 'subject_keywords': [], 'unread_only': False, 'limit': 5, 'want_body': False}

    # unread intent
    if any(w in msg for w in ['unread', 'new ', "haven't read", 'not read']):
        result['unread_only'] = True

    # Intent to read a specific email in full (summarize / reply / open / 'what does it say')
    if any(w in msg for w in ['summari', 'reply', 'respond', 'draft', 'read the', 'read that',
                              'open the', 'open that', 'what does', "what's in", 'whats in', 'tell me about']):
        result['want_body'] = True
        result['limit'] = 3

    # 'from X' sender hint
    from_match = re.search(r'\bfrom\s+([a-zA-Z0-9._%+\-@]+)', msg)
    if from_match:
        result['sender'] = from_match.group(1).strip()

    # 'the X email/one/message' → focus term (matched against sender or subject)
    if not result['sender']:
        focus = re.search(r'\bthe\s+([a-z0-9]{3,})\s+(?:email|one|message|mail)\b', msg)
        if focus and focus.group(1) not in ('first', 'second', 'third', 'last', 'latest', 'next'):
            result['sender'] = focus.group(1).strip()

    # 'about X' / 'regarding X' subject keywords
    about_match = re.search(r'\b(?:about|regarding|re:|subject)\s+["\']?([^"\',.?!]+)', msg)
    if about_match:
        result['subject_keywords'] = about_match.group(1).strip().split()

    # quantity hints
    num_match = re.search(r'\b(\d+)\s+email', msg)
    if num_match:
        result['limit'] = min(int(num_match.group(1)), 20)
    elif any(w in msg for w in ['latest', 'recent', 'last']):
        result['limit'] = 5
    elif 'all' in msg:
        result['limit'] = 20

    return result

# Test our phrase
test_phrase = 'tell me about my latest emails'
result = _extract_email_search_terms(test_phrase)
print(f'Search terms for "{test_phrase}":')
print(result)
print()
print('Want body:', result['want_body'])
print('Limit:', result['limit'])

# Test a few more
test_phrases = [
    'show me my emails from instagram',
    'what emails do I have from work',
    'any new email from john',
    'summarize the latest email from instagram'
]

for phrase in test_phrases:
    result = _extract_email_search_terms(phrase)
    print(f'\n"{phrase}":')
    print(f'  want_body: {result["want_body"]}')
    print(f'  limit: {result["limit"]}')
    print(f'  sender: {result["sender"]}')
