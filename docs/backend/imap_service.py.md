# Mindbase Backend - imap_service.py

## Overview
IMAP email service that handles synchronization and retrieval of email messages from mail servers. Provides secure IMAP/SIMAP connections, email fetching, parsing, and local caching with full Gmail and standard IMAP provider support.

## Responsibilities
- Establish secure connections to IMAP mail servers (SSL/TLS)
- Authenticate using username and app password (OAuth not used)
- Synchronize inbox folders and fetch new email messages
- Parse raw email messages into structured format
- Cache emails locally in SQLite database for offline access
- Support folder selection (INBOX, Sent, Drafts, custom folders)
- Provide incremental synchronization to avoid duplicate downloads
- Handle connection management, disconnections, and error recovery
- Extract email metadata: sender, recipients, subject, date, body
- Support both plain text and HTML email bodies
- Generate searchable snippets for email content
- Manage connection state and provide status queries
- Work seamlessly with the database layer for persistence

## Key Classes & Methods

### EmailService
Singleton class handling all IMAP operations.

#### Connection Management
- `connect(email, password, host="imap.gmail.com", port=993)`: 
  Establish secure IMAP connection
  - Uses IMAP_SSL for port 993 (standard for secure IMAP)
  - Supports custom hosts and ports for non-Gmail providers
  - Authenticates with provided credentials
  - Tests connection with NOOP command after login
  - Stores connection state in instance variable

- `disconnect()`: 
  Gracefully close IMAP connection
  - Logs out from server if connected
  - Closes socket connection
  - Resets connection state

- `is_connected()`: 
  Check if IMAP connection is active
  - Returns boolean connection status
  - Used by API endpoints to gate email operations

- `account_email()`: 
  Get the email address of the connected account
  - Returns the username used for connection
  - Empty string if not connected

#### Email Synchronization
- `sync_inbox(db, max_results=50, unread_only=False, folder="INBOX")`: 
  Main synchronization function
  - Selects specified folder (defaults to INBOX)
  - Searches for messages based on criteria
  - Fetches message headers and bodies in batches
  - Parses each message into components
  - Checks database for existing messages to avoid duplicates
  - Stores new messages in EmailDB table
  - Returns list of newly synced EmailDB objects
  - Supports limiting results and unread-only filtering

- `fetch_message(db, uid_or_id)`: 
  Fetch specific message by UID or database ID
  - Used when detailed view of specific email needed
  - Falls back to local cache if available
  - Fetches from server if not cached or stale

#### Email Parsing
- `_parse_raw_email(raw_message)`: 
  Convert raw IMAP FETCH response to structured format
  - Parses email headers (From, To, Subject, Date, etc.)
  - Extracts body parts (plain text and HTML)
  - Handles multipart/mixed messages (attachments noted)
  - Decodes MIME encoding (quoted-printable, base64)
  - Returns dictionary with all components
  - Missing parts handled gracefully (None or empty string)

- `_extract_body_parts(email_message)`: 
  Separate plain text and HTML bodies from multipart email
  - Prefers plain text for processing when both available
  - Stores HTML separately for rich display options
  - Handles text/plain and text/html subtypes
  - Notes presence of attachments without storing them

- `_generate_snippet(body, length=200)`: 
  Create searchable snippet from email body
  - Strips HTML tags if HTML body provided
  - Normalizes whitespace
  - Truncates to specified length with ellipsis
  - Used for preview in email listings

#### Message Storage
- `_store_email(db, parsed_email)`: 
  Store parsed email in SQLite database
  - Checks if not duplicated
  - Creates new EmailDB record with all
- Message-ID headers Message-ID (for deduplication)`
- update existing record if changed (flags, etc.)
  - Handles is_unread flag updates properly
  - Stores timestamps in UTC for consistency
  - Returns the EmailDB object (new or existing)

#### Utility Methods
- `_get_message_list(db, criteria)`: 
  Helper to fetch message UIDs matching search criteria
  - Supports search by: sender, subject, date range, flags
  - Builds IMAP SEARCH command from criteria
 
- `_mark_as_read(db, uid_list)`: 
  Mark specific messages as read on server
  - Sets \Seen flag via IMAP STORE command
  - Updates local is_unread flag accordingly
 
- `_get_folder_list()`: 
  Retrieve list of available folders on IMAP server
  - Returns folder names with hierarchy separators
 
- `_select_folder(folder)`: 
  Switch currently selected IMAP folder
  - Handles folder name encoding for IMAP protocol
  - Returns message count in folder if successful

## Data Model

### EmailDB (SQLAlchemy Model)
Fields for cached email messages:
- `id`: Primary key ( auto-increment)
- `message_id`: Unique Message-ID from email headers (for deduplication)
- `sender`: Email address of sender (From header)
- `recipients`: To header (comma-separated list)
- `cc_recipients`: CC header (comma-separated list)
- `bcc_recipients`: BCC header (comma-separated list)
- `subject`: Email subject line
- `body`: Plain text body content
- `html_body`: HTML body content (if present)
- `snippet`: Searchable text preview (first 200 chars of body)
- `received_at`: DateTime when email was received (from Date header)
- `is_unread`: Boolean flag indicating read/unread status
- `folder`: Folder where message is stored (default: INBOX)
- `size_bytes`: Approximate size of message in bytes
- `has_attachments`: Boolean indicating presence of attachments
- `created_at`: Timestamp when record was created in local DB
- `updated_at`: Timestamp when record was last updated

## Connection Security

### Encryption
- Uses IMAP_SSL (port 993) for all connections by default
- TLS encryption for IMAP communication
- Alternative: STARTTLS on port 143 (less common)
- No plaintext IMAP support (security requirement)

### Authentication
- Username and password authentication
- Designed for app passwords (not main account passwords)
- Password stored temporarily in memory only
- Credentials used only during connection establishment
- No persistent storage of credentials in this module
- Email credentials stored separately in `data/email_config.json`

## Folder Support

### Standard Folders
- `INBOX`: Primary inbox (default)
- `Sent`: Sent messages
- `Drafts`: Unsent drafts
- `Trash`: Deleted messages
- `Spam`/`Junk`: Spam-filtered messages
- `Archive`: Archived messages

### Custom Folders
- Supports any user-created folders
- Hierarchical folder notation supported (using server separator)
- Folder names encoded according to IMAP standards
- Personal namespaces respected

## Synchronization Strategy

### Incremental Sync
- Tracks last synchronization time per folder
- Uses IMAP SEARCH commands to find new messages since last sync
- Falls back to full sync if state unavailable or corrupted
- UIDVALIDITY checking to detect mailbox resets
- UID-based fetching to avoid re-downloading same messages

### Conflict Resolution
- Local database considered source of truth for flags
- Server state wins for message existence (new/deleted)
- Read/unread status synchronized bidirectionally
- Other flags (flagged, answered) handled as appropriate

### Performance Optimizations
- Batch fetching: Retrieve multiple messages in single command
- Header-only preview: Option to fetch just headers first
- Connection reuse: Single connection used for multiple operations
- Selective fetching: Only download parts needed (headers vs full body)

## Usage Patterns

### Connecting to Email
```python
# Connect to Gmail (default)
success = email_service.connect(
    email="user@gmail.com",
    password="app_password_here"
)

# Connect to other IMAP provider
success = email_service.connect(
    email="user@yahoo.com",
    password="app_password",
    host="imap.mail.yahoo.com",
    port=993
)

# Check connection status
if email_service.is_connected():
    print(f"Connected as {email_service.account_email()}")
```

### Synchronizing Email
```python
# Sync recent inbox (default: 50 messages)
new_emails = email_service.sync_inbox(db)
print(f"Synced {len(new_emails)} new messages")

# Sync only unread messages
unread_emails = email_service.sync_inbox(
    db, 
    unread_only=True,
    max_results=20
)

# Sync specific folder
sent_emails = email_service.sync_inbox(
    db,
    folder="[Gmail]/Sent Mail"
)
```

### Fetching Specific Messages
```python
# Get specific email by database ID
email = email_service.fetch_message(db, email_id=123)

# Access components
print(f"From: {email.sender}")
print(f"Subject: {email.subject}")
print(f"Body: {email.body[:200]}...")
```

### Disconnecting
```python
# Cleanly disconnect when done
email_service.disconnect()
```

## Integration Points

### Called From
- `main.py`: In email API endpoints (`/api/email/*`)
- Background tasks for automatic synchronization
- Manual sync triggered by user action

### Dependencies
- `built-in imaplib`: Standard Python IMAP client (no external deps)
- `email`: Standard Python email parsing library
- `database.py`: For EmailDB model and session management
- `models.py`: For Pydantic models in API endpoints
- `config.py`: For potential configuration values

### Related Modules
- Works with `intelligence.py` to provide email context in chat
- Can synchronize important emails to `memory.py` for long-term remembrance
- Used by document Q&A if emails need to be analyzed as sources

## Special Features

### Gmail-Specific Handling
- Recognizes Gmail-specific folder naming: `[Gmail]/Sent Mail`
- Handles Gmail's label system IMAP mapping appropriately
- Optimized searches for Gmail-specific flags
- Preserves Gmail conversation threading hints when available

### Attachment Awareness
- Detects presence of attachments without downloading them
- Sets `has_attachments` flag based on Content-Type headers
- Notes attachment filenames in logs if needed for debugging
- Does not store attachment data locally (privacy and space)

### Date Handling
- Robust date parsing handles various email date formats
- Converts to UTC datetime for storage and comparison
- Preserves original Date header in received_at field
- Handles timezone information in email headers appropriately

### Search Capabilities
- Supports searching by: sender, recipient, subject, date range
- Enables unread-only and flag-based filtering
- Date ranges: "today", "yesterday", "past week", "MM/DD/YYYY"
- Combines multiple criteria in single IMAP SEARCH when efficient

### Connection Resilience
- Automatic reconnection on transient failures
- Keep-alive mechanisms to prevent timeouts
- Graceful handling of server-side disconnections
- Clear error messages for authentication failures
- Distinguishes between network, auth, and server errors

## Error Handling

### Connection Errors
- Network timeout: Clear "Could not reach mail server" message
- Connection refused: Suggests checking host/port settings
- TLS/SSL errors: Indicates encryption problems
- Max retries exceeded: Fails after several attempts

### Authentication Errors
- Invalid credentials: Clear "Sign-in failed" message
- Suggests using app password not regular password
- Account locked: Indicates possible security lockout
- App password required: Specific guidance for Gmail/2FA

### Synchronization Errors
- Mailbox not found: Indicates incorrect folder name
- Message fetch failed: Skips specific message, continues
- Partial sync: Returns what was able to be synced
- Database errors: Transactions rolled back, error logged

### Parsing Errors
- Malformed headers: Uses defaults or empty values
- Unparseable dates: Uses current time as fallback
- Corrupted MIME structure: Extracts what possible
- Character encoding issues: Attempts multiple decodings

## Performance Characteristics

### Initial Sync
- Time proportional to number of messages in mailbox
- Typical: 1-5 seconds per 100 messages (depends on server and connection)
- Bottlenecks: Network latency, message download, parsing

### Incremental Sync
- Typically <1 second for checking new messages
- Scales with number of new messages, not total mailbox
- Most operations complete in under 500ms for typical usage

### Memory Usage
- Connection object: Minimal overhead
- Message processing: Processes one message at a time
- Does not load entire mailbox into memory
- Database handles persistence efficiently

### Bandwidth Efficiency
- Only downloads new messages since last sync
- Header-first option available for preview mode
- Attachments not downloaded unless explicitly requested
- Text content compressed during transfer implicitly

## Security & Privacy

### Credential Handling
- Passwords never stored in this module
- Only used during connection establishment
- Zero persistence of credentials in memory after use
- Credentials cleared immediately after connection attempt

### Data Privacy
- All email data stored locally in `data/workspace.db`
- No email content transmitted externally
- IMAP credentials only sent to configured mail server
- Local storage encryption dependent on system measures
- User can delete all email data via application

### Compliance
- Follows IMAP RFC standards (RFC 3501)
- Uses standard ports and encryption methods
- Compatible with major email providers (Gmail, Yahoo, Outlook, etc.)
- Respects server-side message flags and state

## Limitations & Considerations

### Attachment Handling
- Current implementation does not download or store attachments
- Attachment presence noted but content not accessible
- Future enhancement: optional attachment download with user consent
- Security consideration: automatic attachment download risky

### Folder Synchronization
- Primary focus on INBOX synchronization
- Other folders syncable but not automatic by default
- Sent folder synchronization available but manual
- Custom folder support complete but requires explicit folder specification

### Performance with Large Mailboxes
- Initial sync of very large mailboxes (>50k messages) may take time
- Incremental sync remains efficient regardless of total size
- Consider archiving old messages for better performance
- Database indexes keep lookups fast even with large datasets

### Connection Limits
- Respects provider-imposed connection limits
- Single connection used where possible
- Connection pooling not implemented but may be added
- Recommended: disconnect when not actively using email