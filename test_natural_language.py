import requests
import json

def test_phrase(phrase, conv_id):
    '''Test if a phrase is detected as an email query'''
    try:
        response = requests.post(
            f"http://localhost:8000/api/chat/messages",
            headers={"Content-Type": "application/json"},
            data=json.dumps({
                "message": phrase,
                "conversation_id": conv_id
            }),
            timeout=10
        )
        
        # Extract the meta data from the first line of the SSE response
        lines = response.text.strip().split('\n')
        meta_line = None
        for line in lines:
            if line.startswith('data: {"meta":'):
                meta_line = line
                break
        
        if meta_line:
            # Extract JSON from the line
            json_str = meta_line[6:]  # Remove 'data: ' prefix
            meta_data = json.loads(json_str)
            intent = meta_data.get('intent', 'unknown')
            context = meta_data.get('context', [])
            actions = meta_data.get('actions', [])
            
            # Check if email context was retrieved
            email_action = any(action.get('type') == 'email_context' for action in actions)
            
            return {
                'phrase': phrase,
                'intent': intent,
                'context': context,
                'has_email_action': email_action,
                'is_email_related': intent == 'email' or email_action
            }
        else:
            return {
                'phrase': phrase,
                'error': 'Could not parse meta data',
                'raw_response': response.text[:200]
            }
    except Exception as e:
        return {
            'phrase': phrase,
            'error': str(e)
        }

# Test phrases
test_phrases = [
    "tell me about my latest emails",
    "show me my emails from instagram",
    "what emails do I have from work",
    "check my mail",
    "look at my messages",
    "do i have any emails today",
    "any new email from john",
    "summarize the latest email from instagram",
    "give me a summary of this email",
    "show me what is in my inbox",
    "are there any emails from amazon",
    "i want to see my recent messages",
    "did i get any email today",
    "what's in my mailbox",
    "look for emails about meeting"
]

print("Testing Natural Language Email Detection")
print("=" * 60)

# Get a conversation ID for testing
try:
    conv_response = requests.post(
        "http://localhost:8000/api/chat/conversations",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"title": "Test Conv"})
    )
    conv_id = conv_response.json()['id']
    print(f"Using conversation ID: {conv_id}\n")
except:
    conv_id = "test-conv-id"  # Fallback
    print("Using fallback conversation ID\n")

email_count = 0
total_count = len(test_phrases)

for phrase in test_phrases:
    result = test_phrase(phrase, conv_id)
    
    if 'error' in result:
        print(f"✗ {result['phrase']}")
        print(f"  Error: {result['error']}")
    else:
        is_email = result['is_email_related']
        status = "✓ EMAIL" if is_email else "✗ NOT EMAIL"
        print(f"{status} {result['phrase']}")
        
        if is_email:
            email_count += 1
            # Show additional details for email queries
            if result['intent'] == 'email':
                print(f"    Intent: {result['intent']}")
            if result['has_email_action']:
                print(f"    Has email context: Yes")
        
    print()

print("=" * 60)
print(f"Results: {email_count}/{total_count} phrases detected as email-related")
print(f"Success rate: {email_count/total_count*100:.1f}%")

if email_count == total_count:
    print("\n🎉 SUCCESS: All natural language phrases are now detected as email queries!")
    print("Users no longer need to memorize specific keywords!")
else:
    print(f"\n⚠️  {total_count - email_count} phrases still need work")
