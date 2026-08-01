# Mindbase Frontend - js/chat.js

## Overview
Handles all chat interface functionality including message rendering, user input processing, scrolling behavior, message animations, and integration with the backend's streaming chat API. Manages the chat view state and user interaction patterns.

## Responsibilities
- Render chat messages from user and assistant
- Handle user input (text entry, sending messages)
- Manage chat scrolling behavior (auto-scroll, manual scroll detection)
- Process and display streaming responses from backend
- Handle message actions (copy, edit, delete, react)
- Manage chat input states (placeholder, disabled, loading)
- Handle file attachments and media in chat
- Implement chat-specific keyboard shortcuts
- Manage message bubbles and avatars
- Handle chat loading and error states
- Coordinate with app.js for view lifecycle events
- Manage chat history and pagination
- Implement message search and filtering
- Handle message selection and bulk operations
- Manage chat-specific UI components (typing indicators, etc.)

## Chat Interface Structure

### HTML Structure
```html
<div id="chat-container">
    <!-- Messages Area -->
    <div id="chat-messages" class="chat-messages">
        <!-- Individual messages go here -->
        <div class="message message-user">
            <div class="message-avatar">
                <!-- User avatar -->
            </div>
            <div class="message-content">
                <div class="message-header">
                    <div class="message-author">You</div>
                    <div class="message-timestamp">10:30 AM</div>
                </div>
                <div class="message-body">
                    <!-- Message text content -->
                </div>
                <div class="message-actions">
                    <!-- Action buttons: copy, edit, delete, react -->
                </div>
            </div>
        </div>
        
        <div class="message message-assistant">
            <div class="message-avatar">
                <!-- Assistant avatar -->
            </div>
            <div class="message-content">
                <div class="message-header">
                    <div class="message-assistant-name">Mindbase</div>
                    <div class="message-timestamp">10:30 AM</div>
                    <div class="message-model-badge">mistral</div>
                </div>
                <div class="message-body">
                    <!-- Message text content -->
                </div>
                <div class="message-actions">
                    <!-- Action buttons -->
                </div>
            </div>
        </div>
        
        <!-- Typing indicator -->
        <div class="message typing-indicator">
            <div class="message-avatar">
                <!-- Assistant avatar -->
            </div>
            <div class="message-content">
                <div class="message-body typing">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Input Area -->
    <div id="chat-input" class="chat-input">
        <div class="input-wrapper">
            <button id="chat-attach" class="input-button" title="Attach file">
                <i class="icon-attach"></i>
            </button>
            <textarea id="chat-message" class="chat-textarea" 
                      placeholder="Ask Mindbase..." 
                      rows="1" 
                      maxlength="5000"></textarea>
            <div class="input-actions">
                <button id="chat-send" class="input-button send-button" title="Send message">
                    <i class="icon-send"></i>
                </button>
            </div>
        </div>
        <div class="input-hints">
            <!-- Hint text: Ctrl+Enter to send, etc. -->
        </div>
    </div>
</div>
```

### CSS Classes (from globals.css and page-theme.css)
- `.chat-messages`: Scrollable container for messages
- `.message`: Base message styling
- `.message-user`: User message styling (right-aligned)
- `.message-assistant`: Assistant message styling (left-aligned)
- `.message-avatar`: Avatar container
- `.message-content`: Message content wrapper
- `.message-header`: Message header (author, timestamp)
- `.message-body`: Message text content
- `.message-actions`: Message action buttons
- `.chat-input`: Input area container
- `.chat-textarea`: Text input field
- `.input-button`: Icon buttons (attach, send)
- `.send-button`: Send button styling
- `.typing-indicator`: Shows when assistant is typing
- `.typing-dot`: Animated typing dots

## Key Functions

### `init()`
Initializes the chat module.
- Sets up DOM element references
- Binds event listeners
- Initializes chat state
- Sets up message rendering systems
- Configures scroll behavior
- Initializes emoji picker andoji picker if available
- Sets up file upload handling
- Registers with app.js for lifecycle events

### `destroy()`
Cleans up the chat module.
- Removes event listeners
- Clears timers and intervals
- Resets chat state
- Clears message containers
- Deregisters from app.js

### `renderMessage(messageData, options)`
Renders a single chat message in the messages container.
- Parameters:
  - `messageData`: Object containing message properties
  - `options`: Rendering options (prepend, animate, etc.)
- Handles both user and assistant messages
- Applies appropriate styling based on message type
- Sets up message actions and event listeners
- Returns the rendered DOM element

### `renderMessageList(messages, options)`
Renders a list of messages.
- Clears or appends to existing messages
- Handles pagination (prepend for older messages)
- Applies animations if specified
- Updates scroll position based on options
- Returns array of rendered elements

### `clearMessages()`
Removes all messages from the chat container.
- Used when starting new conversation
- Resets chat state
- Clears message DOM elements

### `scrollToBottom(options)`
Scrolls the chat container to the bottom.
- Parameters:
  - `options`: 
    - `smooth`: Boolean for smooth scrolling
    - `force`: Boolean to force scroll even if user manually scrolled
    - `offset`: Pixel offset from bottom
- Respects user manual scrolling unless forced
- Animates scroll when smooth is true

### `handleUserInput()`
Processes user input from the chat textarea.
- Gets current text value
- Validates input (not empty, within limits)
- Clears input after sending
- Triggers message sending process
- Handles Shift+Enter for new line
- Handles Enter for sending (unless shift held)

### `sendMessage(messageContent, options)`
Sends a message to the backend and handles the response.
- Parameters:
  - `messageContent`: Text content to send
  - `options`: 
    - `conversationId`: Target conversation
    - `model`: Specific model to use
    - `temperature`: Sampling temperature
    - `agentPrompt`: Custom agent instructions
- Creates user message object and renders it
- Initiates streaming request to backend
- Handles response chunks and updates UI
- Manages loading states and error handling
- Updates conversation history

### `handleStreamingResponse(stream, messageId)`
Processes a streaming response from the backend.
- Parameters:
  - `stream`: Async iterable from API call
  - `messageId`: ID of the user message being responded to
- Handles different chunk types:
  - `meta`: Intent, context, actions metadata
  - `content`: Text chunks to append to response
  - `agent_action`: Actions taken by agent
  - `done`: Stream completion with final metadata
- Updates typing indicator visibility
- Appends content to assistant message
- Handles message completion and cleanup

### `setTypingIndicator(visible)`
Shows or hides the typing indicator.
- Parameters:
  - `visible`: Boolean to show/hide indicator
- Updates DOM visibility
- Adjusts scrolling behavior when shown/hidden

### `setInputState(state)`
Sets the chat input to a specific state.
- Parameters:
  - `state`: One of 'idle', 'loading', 'disabled', 'error'
- Updates input appearance and behavior
- Shows appropriate placeholder text
- Enables/disables send button as needed

### `insertAtCursor(text)`
Inserts text at the current cursor position in textarea.
- Preserves scroll position
- Handles selection replacement
- Works across different browsers
- Used for emoji insertion, slash commands, etc.

### `getInputValue()`
Gets the current value of the chat textarea.
- Returns trimmed string
- Handles placeholder text correctly

### `clearInput()`
Clears the chat textarea.
- Resets value to empty string
- Triggers input event for validation
- Returns focus to textarea

### `focusInput()`
Focuses the chat textarea.
- Attempts to focus textarea
- Handles focus timing issues
- Selects existing text if desired

### `handleFileUpload(file)`
Processes a file selected for upload.
- Validates file type and size
- Creates preview if applicable (image, video, etc.)
- Uploads file via API
- Sends upload result as part of message
- Handles upload progress and errors

### `renderAttachmentPreview(file)`
Creates a preview for an attached file.
- Different handling for image, video, audio, document types
- Shows file icon and metadata for unsupported previews
- Returns DOM element for preview
- Handles large files gracefully

### `handleMessageActions(event)`
Handles clicks on message action buttons.
- Delegates to specific handlers based on action type
- Supports: copy, edit, delete, react, reply, etc.
- Shows appropriate UI for each action
- Updates message state as needed

### `copyMessageText(messageElement)`
Copies the text content of a message to clipboard.
- Handles selection correctly
- Provides user feedback via toast
- Works across different browsers

### `startMessageEdit(messageElement)`
Puts a message into edit mode.
- Replaces message body with textarea
- Preserves original content for cancel
- Handles save and cancel actions
- Updates message via API when saved

### `deleteMessage(messageElement)`
Deletes a message from the chat.
- Shows confirmation dialog
- Removes message from DOM
- Sends delete request to backend (if applicable)
- Updates UI appropriately

### `addMessageReaction(messageElement, reaction)`
Adds a reaction (emoji) to a message.
- Shows reaction picker
- Sends reaction to backend
- Updates message display with reaction count
- Handles removing/reducing reactions

### `showContextMenu(event, messageElement)`
Shows context menu for a message.
- Positioned at click location
- Contains relevant actions for message type
- Handles clicking outside to close
- Supports keyboard navigation

### `handleKeyboardShortcuts(event)`
Processes keyboard shortcuts in chat input.
- Ctrl+Enter: Send message
- Enter: Send message (unless shift held)
- Escape: Clear input or cancel action
- Up/Down: Navigate message history
- Tab: Insert tab character or autocomplete
- Custom slash commands: /task, /remind, etc.

### `loadMessageHistory(options)`
Loads older messages for pagination.
- Parameters:
  - `beforeMessageId`: Load messages before this ID
  - `limit`: Number of messages to load
- Prepends messages to chat container
- Adjusts scroll position to maintain view
- Shows loading indicator during fetch
- Handles end-of-history detection

### `searchMessages(query, options)`
Searches through message history.
- Parameters:
  - `query`: Search text
  - `options`: Case sensitivity, regex, etc.
- Highlights matching terms in messages
- Returns matching message IDs
- Highlights matches in UI
- Clears search when empty query

### `selectMessage(messageElement)`
Selects a message for bulk operations.
- Toggles selected state
- Updates selection count UI
- Enables/disables bulk action buttons
- Supports shift-click for range selection

### `clearSelection()`
Clears all selected messages.
- Removes selected styling
- Resets selection count
- Disables bulk action buttons

### `performBulkAction(action)`
Performs an action on selected messages.
- Parameters:
  - `action`: One of delete, copy, archive, etc.
- Applies action to all selected messages
- Updates UI and chat state
- Clears selection after completion

### `updateTypingIndicator()`
Updates the typing indicator animation.
- Called regularly via requestAnimationFrame
- Manages the bouncing dots effect
- Handles visibility and positioning

### `adjustTextareaHeight()`
Automatically adjusts textarea height based on content.
- Prevents overflow
- Sets maximum height
- Maintains minimum height
- Called on input and window resize

### `handleResponsiveLayout()`
Adapts chat layout for different screen sizes.
- Adjusts message max-width
- Modifies padding and margins
- Handles input area layout changes
- Updates avatar sizes

### `setConversationId(conversationId)`
Sets the current conversation ID.
- Used for API calls
- Updates window title or header if needed
- Resets chat state for new conversation

### `getConversationId()`
Gets the current conversation ID.

## Chat State Management

### Message State
Each message in the chat maintains:
- `id`: Unique message identifier
- `conversationId`: Associated conversation
- `role`: 'user' or 'assistant'
- `content`: Message text content
- `timestamp`: When message was sent/received
- `model`: Model used for assistant messages
- `intent`: Detected intent (for assistant messages)
- `contextSources`: Sources of context used
- `actionsTaken`: Actions performed during processing
- `status`: 'sending', 'sent', 'failed', 'edited'
- `attachments`: List of attached files
- `reactions`: Emoji reactions with counts
- `edited`: Timestamp if message was edited
- `replyTo`: ID of message being replied to (if any)
- `metadata`: Additional message-specific data

### UI State
The chat module tracks:
- `isLoading`: Boolean for loading states
- `isUserTyping`: Boolean for user input state
- `isAssistantTyping**: Boolean for assistant response state
- `scrollPosition`: Last known scroll position
- `userScrolledManually`: Flag indicating if user scrolled
- `selectedMessages`: Set of currently selected message IDs
- `searchQuery`: Current search query if any
- `searchResults`: Set of matching message IDs
- `currentConvesationId**: ID of active conversation
- `messageCache**: Cache of rendered message elements
- `lastMessageId**: ID of most recent message
- `firstMessageId**: ID of oldest loaded message
- `hasMoreHistory**: Boolean indicating if more messages exist
- `isAtBottom**: Boolean indicating if scrolled to bottom

### Chat state
- `inputHeight**: Current textarea height
- `maxInputHeight**: Maximum allowed textarea height errors
- `pendingActions**: Queue of actions to process when ready

## Event Handling

### DOM Events
- `textarea input`: Adjust height, validate input, enable/disable send
- `textarea keydown`: Handle keyboard shortcuts, new line vs send
- `textarea focus`: Clear any error states, show placeholder
- `textarea blur`: Validate final input, save draft if needed
- `send-button click`: Send current message
- `attach-button click`: Open file picker
- `file-input change`: Process selected file(s)
- `chat-messages scroll`: Detect user scrolling, update state
- `window resize`: Adjust layout, textarea height
- `visibility change`: Pause/resume certain activities
- `document click`: Close context menus, clear selections
- `message click`: Select message, handle double-click
- `message dblclick`: Select word, edit message (configurable)
- `contextmenu`: Show context menu for message
- `keydown`: Global shortcuts (Ctrl+F for search, etc.)

### Custom Events (via app.js event system)
- `app-ready`: Initialize chat when application ready
- `app-destroy`: Cleanup chat module
- `view-loading`: Prepare for view unload
- `view-loaded`: Initialize when chat view loaded
- `view-unloading`: Cleanup when chat view unloaded
- `view-unloaded`: Final cleanup
- `state-change`: Respond to relevant state changes
- `conversation-change`: Handle conversation switching
- `message-sent`: Confirm message was sent
- `message-received`: Handle incoming message (if applicable)
- `typing-start`: Show typing indicator
- `typing-end**: Hide typing indicator
- `scroll-change**: Respond to scroll position changes
- `resize`: Handle window size changes
- `visibility-change**: Handle tab visibility
- `theme-change**: Update chat appearance for theme
- `language-change**: Update interface text
- `accessibility-change**: Adapt for accessibility needs

## Message Rendering

### User Messages
- Right-aligned in chat container
- Background: var(--primary)
- Text color: white
- Border-radius: rounded except bottom-left
- Avatar: User avatar or initials
- Timestamp: Right-aligned in header
- Actions: Left-aligned in message footer

### Assistant Messages
- Left-aligned in chat container
- Background: var(--bg-secondary)
- Text color: var(--text-primary)
- Border: 1px solid var(--border-color)
- Border-radius: rounded except bottom-right
- Avatar: Assistant avatar or logo
- Timestamp: Left-aligned in header
- Model badge: Shows model used (if available)
- Actions: Right-aligned in message footer

### System Messages
- Full-width or centered
- Background: var(--bg-tertiary)
- Text color: var(--text-muted)
- Font-size: smaller
- Text-align: center
- Padding: reduced
- Used for status messages, notifications

### Loading States
- Skeleton shimmer animation during loading
- Placeholder avatars
- Loading text: "Mindbase is thinking..."
- Reduced opacity for interactive elements

### Error States
- Error background: var(--danger) at 10% opacity
- Error text color: var(--danger)
- Error icon: exclamation triangle
- Retry button: prominent call-to-action
- Message: "Failed to send message. Try again?"

### Attachments
- Image attachments: Preview thumbnail
- Video attachments: Play button overlay
- Audio attachments: Waveform visualization
- Document attachments: File icon with name and size
- File type badges: PDF, DOC, XLS, etc.
- Download prompt: Click to download or view

### Actions Menu
- Copy: Copy message text to clipboard
- Edit: Put message in edit mode (user messages only)
- Delete: Remove message (with confirmation)
- React: Add emoji reaction
- Reply: Prefix input with reply to this message
- Select: Toggle selection for bulk operations
- More: Additional options (copy raw JSON, etc.)

## Typing Indicator

### Animation
- Three dots that bounce in sequence
- Each dot: 0.4s delay, 0.6s duration, ease-in-out
- Loop: infinite
- Position: Left-aligned in message bubble
- Color: var(--text-secondary) or var(--primary) for accent

### States
- Showing: When assistant is generating response
- Hiding: When user is typing or no activity
- Positioning: Appears at bottom of message list
- Scrolling: Container scrolls to accommodate indicator

### Implementation
- Uses CSS animation for smooth performance
- DOM element reused rather than recreated
- Visibility toggled via class addition/removal
- Respects reduced motion preferences

## File Attachments

### Supported Types
- **Images**: JPG, PNG, GIF, SVG, WebP
- **Videos**: MP4, WebM, OGG
- **Audio**: MP3, WAV, OGG, M4A
- **Documents**: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, MD, CSV
- **Archives**: ZIP, RAR, 7Z (limited preview)
- **Code**: Syntax highlighting for common languages

### Processing Flow
1. **Selection**: User selects file via file picker or drag-drop
2. **Validation**: Check file type and size limits
3. **Preview Generation**: 
   - Images: Create thumbnail URL
   - Video/Audio: Create preview thumbnail or waveform
   - Documents: Extract first page or generate icon
   - Others: Show file type icon
4. **Upload**: Send file to backend via multipart/form-data
5. **Integration**: Include upload result in message
6. **Display**: Show attachment in message with preview/actions

### Size Limits
- Configurable maximum file size
- Different limits for different file types
- Client-side validation before upload
- Server-side validation as backup
- Clear error messages when limits exceeded

### Drag and Drop
- Supports dragging files onto chat input
- Visual feedback during drag (highlight input area)
- Handles multiple files at once
- Prevents default browser behavior
- Works with files from desktop or file explorer

### Paste Handling
- Supports pasting images from clipboard
- Converts clipboard image to blob for upload
- Shows preview before sending
- Handles multiple image pastes
- Works with screenshots and copied images

## Scrolling Behavior

### Auto-Scroll Logic
- Auto-scroll to bottom when:
  - User is at bottom (within threshold)
  - New message arrives
  - User sends a message
  - Typing indicator appears/disappears
- Do NOT auto-scroll when:
  - User has manually scrolled up
  - User is reading older messages
  - Explicitly disabled by options

### Scroll Position Tracking
- Tracks scrollTop and scrollHeight
- Computes distance from bottom
- Threshold: 100px from bottom considered "at bottom"
- Updates state on scroll events
- Uses requestAnimationFrame for smooth handling

### Manual Scroll Detection
- Sets flag when user scrolls manually
- Clears flag when user scrolls back to bottom
- Uses scroll event with throttling
- Respects user intent to read older messages
- Restores auto-scroll when user returns to bottom

### Smooth Scrolling
- Uses element.scrollTo() with behavior: 'smooth'
- Falls back to animation for older browsers
- Configurable duration and easing
- Can be disabled for instant scrolling
- Respects prefers-reduced-media: reduce

### Scroll Restoration
- Remembers scroll position per conversation
- Restores position when returning to conversation
- Handles dynamic height changes
- Uses ID-based scrolling when possible

## Performance Optimizations

### Message Rendering
- Document fragments for bulk message insertion
- Request animation frame for visual updates
- Virtual scrolling for very long conversations (future)
- Message caching: reuse DOM elements when possible
- Batched DOM updates to minimize reflows

### Event Handling
- Debounced resize handler (200ms)
- Throttled scroll handler (100ms)
- Passive event listeners where possible
- Event delegation for message actions
- Weak references for event subscriptions

### Memory Management
- Properly removes event listeners
- Clears timers and intervals
- Nullifies references to prevent leaks
- Limits message cache size
- Clears selection state appropriately

### Network Efficiency
- Request deduplication prevents duplicate API calls
- Message batching for historical loads
- Compression of large responses
- Adaptive loading based on scroll velocity
- Prefetching of likely needed messages

### Rendering Optimizations
- CSS will-change properties for animated elements
- Transform and opacity for animations (GPU accelerated)
- Contain: layout paint for message elements
- Font loading optimization
- Image decoding: async where supported

## Accessibility Features

### Keyboard Navigation
- Tab focus moves through: textarea → send button → attach button → message actions (when focused)
- Arrow keys navigate between messages when focused
- Enter activates focused button or action
- Escape clears input or cancels current action
- Home/End jump to beginning/end of message list
- Page Up/Page Down scroll by viewport
- Ctrl+Home/Ctrl+End jump to absolute start/end

### Screen Reader Support
- ARIA-live region for new message announcements
- ARIA-label on send button: "Send message"
- ARIA-label on attach button: "Attach file"
- Role="log" on messages container for live updates
- Aria-roledescribedby on message elements for context
- Title attribute updated with unread count
- Proper heading structure if implemented
- Alt text for avatars and attachments
- Labels for all form elements

### Color and Contrast
- Message bubbles meet WCAG AA contrast ratios
- Focus outlines visible and sufficient width
- Error states use color + icon + text
- Success states use color + icon + text
- Placeholder text meets contrast minimum
- Disabled states have reduced opacity but sufficient contrast

### Touch and Pointer
- Minimum 44x44pt touch targets for all interactive elements
- Adequate spacing between touch targets
- Visual feedback on touch (pressed state)
- No reliance on hover-only functionality
- Works with zoom up to 200%

### Reduced Motion
- Respects prefers-reduced-media: reduce
- Animations disabled or replaced with static states
- Transitions use fading instead of sliding
- Typing indicator uses pulsing instead of bouncing
- Scroll changes are instant rather than animated
- Feedback uses color change instead of movement

### Error Handling and Recovery
- Error messages are descriptive and actionable
- Provides clear recovery paths (retry, try again, etc.)
- Error states are perceivable through multiple means
- Keyboard focus managed appropriately during errors
- Error recovery does not lose user data

## Internationalization (Future Ready)

### Text Externalization
- All user-facing strings externalized
- Uses i18next or similar framework ready
- Placeholders for dynamic content
- Right-to-left language support built-in
- Date/time formatting localization
- Number formatting localization
- Pluralization handling

### Directionality Support
- CSS logicdir] selectors for LTR/RTL
- Flexbox row-reverse for RTL layouts
- Text-align adjustments for direction
- Mirrored padding/margins for RTL
- Scrollbar positioning consideration
- Icon flipping where appropriate (not all icons)

### Localization Considerations
- Date/time formats vary by locale
- Number formats (decimal/separator)
- Currency formats
- Measurement units
- Paper sizes
- Address formats
- Phone number formats
- Name formats
- Honorifics and titles

## Error Handling

### Message Sending Failures
- Network errors: Show retry button with exponential backoff
- Validation errors: Show field-specific errors below input
- Server errors: Show generic error with support contact
- Timeout errors: Show timeout message with retry option
- Aborted requests: Treat as cancellation, no error shown
- Invalid responses: Show malformed response error

### Rendering Errors
- DOM errors: Log and skip problematic message
- CSS errors: Fallback to basic styling
- Image load errors: Show broken image icon with alt text
- Template errors: Show system message with details
- State errors: Reset to known good state and notify user

### State Errors
- Inconsistent state: Log warning and attempt recovery
- Missing data: Show placeholder with indication of issue
- Corrupted cache: Clear cache and reload from backend
- Sync errors: Provide manual sync option
- Conflicting states: Use timestamp-based resolution

### User Recovery
- Retry buttons: Prominent call-to-action for recovery
- Undo functionality: Where applicable (message deletion, etc.)
- Edit recovery: Restore original content on cancel
- State reset: Option to clear chat and start fresh
- Support links: Provide contact information for persistent errors
- Debug info: Optional display of technical details for advanced users

## Security Measures

### Content Security
- Sanitize all user-generated content before display
- Use trusted types for DOM manipulation when available
- Implement strict CSP for chat module
- Sanitize URLs in link preview generation
- Prevent XSS through message content and attachments
- Safe handling of file names and metadata

### Privacy
- Do not store message content in localStorage
- Clear sensitive data from memory when no longer needed
- Handle file uploads securely (verify scan if applicable)
- Do not log message content to console
- Respect user data minimization principles

### Input Validation
- Validate message length (client and server side)
- Sanitize input for safe display
- Limit file types and sizes for upload
- Validate message metadata structure
- Reject malformed JSON from backend
- Validate URLs before making fetch requests

### Secure Communication
- Use HTTPS for all API calls in production
- Validate SSL certificates
- Implement certificate pinning if needed
- Use secure websockets if real-time features added
- Secure handling of authentication tokens if implemented

## Performance Benchmarks

### Initial Load
- Target: <1000ms to interactive state
- Critical path: HTML → CSS → core JS → chat initialization
- Non-critical: view-specific JS, third-party libraries
- First Contentful Paint: <1500ms
- Time to Interactive: <3000ms on mid-tier device

### Message Rendering
- Target: <16ms per message for 60fps
- Batch rendering: <50ms for 10 messages
- Virtual scrolling target: consistent performance regardless of length
- Memory usage: <50MB for 1000 messages
- DOM node count: <3x message count for efficiency

### Input Latency
- Target: <50ms from keypress to visual feedback
- Debounce: minimal for typing experience
- Frame rate: maintain 60fps during typing
- Input lag: imperceptible to user

### Network Performance
- Time to first byte: <500ms (local network)
- Stream start delay: <200ms after request sent
- Chunk delivery: consistent intervals
- Total transfer time: depends on response length
- Concurrent requests: limited to prevent congestion

### Scrolling Performance
- Scroll event handling: <8ms per event
- Animation smoothness: 60fps maintained
- Layout thrashing: avoided through read/write separation
- Repaint minimization: CSS containment and will-change

### Memory Usage
- Base memory: <20MB for chat module
- Per message: ~20-50KB depending on content
- Image previews: released when scrolled out of view
- Attachments: memory released after upload
- Long conversations: virtualization planned for scale

## Dependencies

### Internal Dependencies
- `api.js`: For backend communication (chatStream method)
- `app.js`: For application lifecycle and state
- `utils.js`: For helper functions (debounce, throttle, etc.)
- `toast.js`: For user notifications

### External Dependencies
- None (uses only native browser APIs)
- Future considerations:
  - Emoji picker library (if custom implementation not sufficient)
  - Markdown renderer (if supporting formatted messages)
  - Syntax highlighter (for code blocks in messages)
  - File type detection library (more accurate than extensions)
  - Virtual scrolling library (for very long conversations)
  - Animation library (for complex transitions if needed)

### Browser Support
| Feature | Support |
|---------|---------|
| Core Chat | All modern browsers |
| Flexbox Layout | Chrome 29+, Firefox 28+, Safari 9+, Edge 12+ |
| CSS Grid | Chrome 57+, Firefox 52+, Safari 10+, Edge 16+ |
| CSS Variables | Chrome 49+, Firefox 31+, Safari 9.1+, Edge 15+ |
| Fetch API | Chrome 42+, Firefox 39+, Safari 10.1+, Edge 14+ |
| AbortController | Chrome 66+, Firefox 57+, Safari ?, Edge 16+ |
| Promise | Chrome 32+, Firefox 29+, Safari 8+, Edge 12+ |
| Class Syntax | Chrome 42+, Firefox 45+, Safari 9+, Edge 13+ |
| Arrow Functions | Chrome 45+, Firefox 22+, Safari 10+, Edge 12+ |
| Let/Const | Chrome 41+, Firefox 36+, Safari 10+, Edge 12+ |
| Template Literals | Chrome 41+, Firefox 34+, Safari 9+, Edge 12+ |
| Destructuring | Chrome 49+, Firefox 41+, Safari 10+, Edge 14+ |
| Modules (ESM) | Chrome 61+, Firefox 60+, Safari 10.1+, Edge 16+ |
| localStorage | Chrome 4+, Firefox 3.5+, Safari 4+, Edge + |
| sessionStorage | Chrome 5+, Firefox 2+, Safari 4+, Edge + |
| IndexedDB | Chrome 23+, Firefox 15+, Safari 7+, Edge 12+ |
| CSS Animations | Chrome 43+, Firefox 16+, Safari 5+, Edge 12+ |
| CSS Transitions | Chrome 26+, Firefox 16+, Safari 6.1+, Edge 12+ |
| Touch Events | Chrome 22+, Firefox 6+, Safari 5+, Edge + |
| Pointer Events | Chrome 55+, Firefox 59+, Safari ?, Edge 12+ |
| Drag and Drop | Chrome 4+, Firefox 3.5+, Safari +, Edge + |

## Implementation Notes

### Coding Style
- Uses modern ES6+ syntax (classes, arrow functions, destructuring)
- Consistent naming: camelCase for variables/functions, UPPER_SNAKE_CASE for constants
- Private methods prefixed with underscore
- JSDoc comments for public methods and complex logic
- Maximum line length: 100 characters
- Indentation: 2 spaces
- Quotes: single quotes for strings, double quotes for HTML attributes
- Trailing commas in multi-line objects and arrays
- Semicolons: always used
- Function declarations: preferred over expressions for hoisting benefits

### Architecture
- Module pattern: self-contained with clear public interface
- Separation of concerns: rendering vs logic vs state
- Event-driven: responds to user actions and system events
- State centralization: chat state managed within module
- DOM minimization: limits direct DOM manipulation
- Performance conscious: considers reflow/repaint costs
- Accessibility first: considers a11y in all implementations
- Mobile responsive: designed for touch interfaces from start

### Error Philosophy
- Fail fast in development with clear errors
- Graceful degradation in production
- User-friendly error messages with recovery options
- Logging appropriate to severity and context
- Error state does not lose user data
- Recovery paths

Data persistence strategy
- Prefer immutable data patterns where possible
- Clone data before passing to callbacks
- Freeze objects that should not be modified
- Use Map/Set for collections when appropriate
- Object pooling for frequently allocated small objects
- Memory leak prevention through proper cleanup

### Testing Considerations
- Highly testable with clear separation of concerns
- Mock API calls for unit testing
- Test DOM manipulation with jsdom or similar
- Test edge cases: empty messages, very long messages, special characters
- Test accessibility with axe-core or similar
- Test performance with benchmarking tools
- Test cross-browser compatibility where feasible
- Test mobile-specific features with device emulation
- Test internationalization with different locales

### Future Enhancements

#### Message Features
- Message threading/replies
- Message pinning and starring
- Message forwarding
- Message quoting in replies
- Message reactions with avatars
- Message editing history
- Message reactions with custom emojis
- Threaded conversations
- Collapsible message threads
- Message search with filters
- Message export/import
- Message bookmarking/saving

#### Input Enhancements
- Rich text formatting (bold, italic, code, etc.)
- Markdown support
- Slash command autocomplete
- Emoji prediction and suggestion
- Message drafts (auto-save)
- Message scheduling
- Voice-to-text input
- Multilingual input support
- Custom keyboard shortcuts
- Input validation and formatting

#### Attachment Improvements
- Drag and drop anywhere in chat
- Multiple file selection with progress
- Image editing (crop, rotate, filter)
- Video trimming and thumbnail selection
- Audio waveform editing
- File compression before upload
- Virus scanning of uploads (if applicable)
- Cloud storage integration (Google Drive, Dropbox, etc.)
- Link preview generation (OpenGraph, Twitter Cards)
- File versioning and history

#### Interface Improvements
- Customizable themes (beyond light/dark)
- Font size adjustment
- Compact and comfortable modes
- Left-handed mode
- Avatar customization
- Message bubble styling options
- Timestamp formatting options
- Read receipts and delivery status
- Message forwarding with context
- Group chat support (future)
- Message reactions with avatars
- Typing indicators with avatars
- Message forwarding with context
- Collapsible message sections
- Message threading UI
- Message collapsible code blocks
- Message spoiler tags
- Message quote chains
- Message pinning to top
- Message scheduling
- Message reminders/follow-ups
- Message translation
- Message summarization
- Message sentiment analysis
- Message language detection

#### Performance Optimizations
- Virtual scrolling for very long conversations
- Message windowing (only render visible messages)
- Scroll caching
- Request idle callback for low-priority work
- Intersection observer for lazy loading
- Service worker for offline chatting
- IndexedDB for persistent message caching
- WebAssembly for heavy computations (if needed)
- Canvas-based rendering for extreme performance
- WebGL for complex visualizations (if needed)
- Request animation frame optimization
- Battery API for power-sensitive devices
- Network information API for adaptive quality

#### Accessibility Enhancements
- Full voice control support
- Better screen reader announcements
- Improved keyboard navigation patterns
- High contrast mode availability
- Font scaling support
- Reduced motion alternatives
- Cognitive load reduction options
- Language-specific accessibility considerations
- Sign language support (video chat extension)
- Alternative input methods support

#### Security Improvements
- End-to-end encryption (future)
- Message expiration/self-destruct
- Screenshot prevention (where possible)
- Forward secrecy
- Key verification functionality
- Secure file sharing with expiration
- Anonymous messaging mode
- Moderation tools
- Content warnings
- Reporting and blocking features
- Audit logging
- Data export and deletion rights
- GDPR/CCPA compliance features