# Mindbase Frontend - index.html

## Overview
The main application shell that serves as the entry point for the Mindbase AI workspace. Contains the primary chat interface, model selector, dock/navigation, and loads all necessary CSS and JavaScript resources.

## Responsibilities
- Provide the main HTML structure for the application
- Load external CSS and JavaScript resources
- Define the chat interface layout (messages, input area)
- Host the application dock for navigation
- Include the model selection dropdown
- Set up event listeners via bundled JavaScript
- Provide container for dynamic page loading
- Include favicon and meta tags for proper display

## Structure & Components

### HTML Structure
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <!-- Meta tags, title, favicon -->
    <!-- CSS links: globals.css, page-theme.css -->
</head>
<body>
    <!-- Main container -->
    <div id="app">
        <!-- Header with model selector and app title -->
        <header>
            <!-- Model dropdown -->
            <!-- App title/logo -->
        </header>
        
        <!-- Main interface -->
        <main>
            <!-- Chat messages container -->
            <div id="chat-messages"></div>
            
            <!-- Chat input area -->
            <div id="chat-input">
                <!-- Text input field -->
                <!-- Send button -->
                <!-- Attachment/clip button -->
            </div>
        </main>
        
        <!-- Dock/navigation -->
        <div id="dock">
            <!-- Dock items for navigation -->
            <!-- Dashboard, Tasks, Calendar, Email, Notes, Memory, Research, Agents, Settings -->
        </div>
    </div>
    
    <!-- JavaScript links -->
    <!-- api.js, app.js, chat.js, dock.js, utils.js, toast.js, etc. -->
</body>
</html>
```

### Key Elements

#### Header Section
- Application title/logo: "Mindbase"
- Model selector dropdown: Allows switching between available Ollama models
- Displays current model name and status indicator

#### Chat Interface
- **Messages Container** (`#chat-messages`):
  - Scrollable area displaying chat messages
  - Messages appear as bubbles with avatars/timestamps
  - Supports different message types: user, assistant, system
  - Automatic scrolling to latest message
  
- **Input Area** (`#chat-input`):
  - Text input field for user messages
  - Send button (paper airplane icon)
  - Attachment button (paperclip icon) for file uploads
  - Enter key to send, Shift+Enter for newline
  - Placeholder text: "Ask Mindbase..."

#### Dock Navigation
- Vertical or horizontal dock (depending on screen size)
- Icons for navigating to different application views:
  - 🏠 Dashboard: Overview of tasks, calendar, etc.
  - 📋 Tasks: Task management interface
  - 📅 Calendar: Calendar view with tasks and events
  - 📧 Email: Email client interface
  - 📝 Notes: Notes creation and management
  - 🧠 Memory: Long-term memory browser/search
  - 🔬 Research: Research agent controls
  - 🤖 Agents: AI agent configuration
  - ⚙️ Settings: Application settings
- Active item highlighting
- Tooltips on hover
- Responsive layout (vertical on wide screens, horizontal on narrow)

## CSS Classes & IDs
- Uses CSS classes from `globals.css` and `page-theme.css`
- Key IDs: `#app`, `#header`, `#chat-messages`, `#chat-input`, `#dock`
- Message styling: `.message`, `.user-message`, `.assistant-message`
- Dock items: `.dock-item`, `.dock-item-active`
- Input styling: `#chat-input input`, `#chat-input button`

## JavaScript Initialization
- Loads and initializes modules from `js/` directory
- Sets up event listeners for:
  - Chat input (send button, Enter key)
  - Dock navigation clicks
  - Model selector changes
  - Window resize events
  - Application lifecycle events
- Initializes application state
- Checks backend connectivity on load

## Responsibilities Delegated to JavaScript
While index.html provides the structure, the actual behavior is implemented in JavaScript files:

### app.js
- Main application controller
- Handles route changes and view loading
- Manages application state
- Coordinates between different modules

### chat.js
- Handles all chat interface logic
- Message rendering and display
- User input handling
- Scrolling behavior
- Message animations and transitions

### dock.js
- Dock rendering and interaction
- Navigation between views
- Active state management
- Responsive behavior (vertical/horizontal dock)

### api.js
- Wrapper for backend API calls
- Handles request/response formatting
- Error handling
- Authentication token management (if applicable)

### utils.js
- Utility functions used across the application
- Date formatting
- String trimming/manipulation
- Helper functions

### toast.js
- Notification system for user feedback
- Success, error, warning, info messages
- Automatic timeout and dismissal

## Integration Points

### CSS Resources
- `css/globals.css`: Design tokens (colors, spacing, etc.) and base styles
- `css/page-theme.css`: Shared chrome styling for consistent look across pages

### JavaScript Modules
All JavaScript modules are loaded via script tags in the HTML:
- `js/api.js` - Backend communication
- `js/app.js` - Application logic
- `js/chat.js` - Chat interface
- `js/dock.js` - Dock navigation
- `js/email.js` - Email-specific functions
- `js/toast.js` - Notifications
- `js/utils.js` - Utilities
- `js/chat.js` - Chat handling (note: duplicate in listing, likely refers to same)

### Backend Communication
- All data fetched from backend via `/api/*` endpoints
- Uses fetch API with proper error handling
- SSE (Server-Sent Events) for streaming chat responses
- JSON format for all requests/responses

### Page Loading
- When dock items are clicked, corresponding HTML pages are loaded
- Pages are fetched from `frontend/pages/` directory
- Main content area updated via AJAX-style loading
- Scripts on loaded pages executed appropriately

## Responsive Design
- Mobile-first approach
- Dock adapts to screen size:
  - Wide screens: Vertical dock on left or right
  - Narrow screens: Horizontal dock on bottom
- Chat interface adjusts to available width
- Input area remains accessible on small screens
- Font sizes and spacing scale appropriately

## Accessibility Features
- Semantic HTML structure
- ARIA labels for interactive elements
- Keyboard navigation support
- Focus management for modal dialogs
- Sufficient color contrast (uses CSS variables)
- Screen reader friendly labels

## Performance Considerations
- Minimal HTML - structure only, behavior in JS
- CSS loaded in head for proper rendering
- JavaScript loaded at end of body for faster initial paint
- Resources cached via browser caching
- Minimizes DOM manipulation on initial load
- Efficient event delegation where possible

## Customization Points
- Application title in header
- Dock items can be added/removed/modified
- Chat interface styling via CSS variables
- Model selector options populated from backend
- Placeholder text and UI text can be modified

## Security Features
- No inline scripts (all behavior in external JS files)
- Content Security Policy ready (nonces can be added)
- Input sanitization handled in JavaScript/backend
- CSRF protection relies on same-origin policy
- No sensitive data stored in DOM

## Usage in Application
Served as the root path (`/`) by the backend's static file handler. All navigation occurs within this single page application - different views are loaded dynamically into the main content area rather than full page reloads.