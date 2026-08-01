# Mindbase Frontend - js/app.js

## Overview
Main application controller that manages the overall application state, routing, view loading, and coordination between different modules. Acts as the central orchestrator for the single-page application.

## Responsibilities
- Manage application state and lifecycle
- Handle client-side routing and navigation
- Load and unload page views based on URL/dock selection
- Initialize and coordinate between different JavaScript modules
- Handle global events (window resize, visibility changes, etc.)
- Manage loading states and progress indicators
- Handle error boundaries and error recovery
- Store and retrieve application preferences
- Coordinate communication between modules via event system
- Manage dock/navigation state and synchronization with URL
- Handle application initialization and cleanup
- Provide global utilities accessible to other modules

## Application Lifecycle

### Initialization Process
1. **DOMContentLoaded**: Wait for DOM to be ready
2. **Module Loading**: Import and initialize all required modules
3. **State Initialization**: Set up initial application state
4. **Route Setup**: Configure URL routing and listeners
5. **Dock Setup**: Initialize navigation dock and event listeners
6. **Initial View Load**: Load the default view (typically dashboard)
7. **Event Binding**: Set up global event listeners
8. **Readiness Signal**: Emit app-ready event for modules to initialize

### State Management
The application maintains several key state objects:

#### `appState`
- `currentView`: Name of currently loaded view
- `currentRoute`: Current URL path
- `viewHistory`: Stack of previously visited views
- `isLoading`: Boolean indicating if async operation in progress
- `error`: Current error state if any
- `userPreferences`: Stored user settings and preferences
- `backendStatus`: Connection status to backend services
- `activeModules`: Set of currently initialized modules

#### Module State Coordination
- Each module registers its state with the app
- App provides getters/setters for cross-module state access
- State changes trigger appropriate UI updates
- State persists certain data across page reloads (via localStorage)

### View Loading and Unloading
When navigating to a new view:
1. **Cancel Operations**: Cancel any ongoing operations in current view
2. **Unload Current View**: Call view's onunload cleanup function
3. **Update State**: Set currentView in appState
4. **Load New View**: Fetch view HTML from frontend/pages/
5. **Initialize View**: Call view's onload initialization function
6. **Bind Events**: Set up view-specific event listeners
7. **Update UI**: Update dock selection, URL, page title
8. **Emit Events**: Notify modules of view change

When unloading a view:
1. **Cleanup Timers**: Clear any setInterval/setTimeout
2. **Remove Event Listeners**: Clean up view-specific listeners
3. **Destroy Instances**: Clean up any class instances created
4. **Save State**: Persist view-specific state if needed
5. **Call onunload**: Allow view to perform cleanup
6. **Clear DOM**: Remove view content from page container

## Routing System

### URL Structure
The application uses hash-based routing for simplicity:
- `#/` or `#dashboard` → Dashboard view
- `#/tasks` → Tasks view
- `#/calendar` → Calendar view
- `#/email` → Email view
- `#/notes` → Notes view
- `#/memory` → Memory view
- `#/research` → Research view
- `#/agents` → Agents view
- `#/settings` → Settings view

### Route Configuration
Routes are defined in a central map:
```javascript
const ROUTES = {
  '': 'dashboard',
  '/': 'dashboard',
  '/dashboard': 'dashboard',
  '/tasks': 'tasks',
  '/calendar': 'calendar',
  '/email': 'email',
  '/notes': 'notes',
  '/memory': 'memory',
  '/research': 'research',
  '/agents': 'agents',
  '/settings': 'settings'
};
```

### Navigation Methods
- `navigateTo(viewName)`: Programmatic navigation
- `goBack()`: Navigate to previous view in history
- `goForward()`: Navigate to next view in history
- `refresh()`: Reload current view
- `handleUrlChange()`: Respond to URL/hash changes
- `updateUrl(viewName)`: Update URL without triggering navigation event

## Module Coordination

### Module Lifecycle
Modules follow this lifecycle:
1. **Registration**: Module registers with app during initialization
2. **Initialization**: App calls module's init() function when needed
3. **Activation**: When view loads, app activates relevant modules
4. **Deactivation**: When view unloads, app deactivates modules
5. **Destruction**: When app shuts down, modules destroy resources

### Communication Patterns
#### Event System
- App provides publish-subscribe event system
- Modules can subscribe to global events
- Modules can publish events for others to listen to
- Events are namespaced to prevent collisions
- Weak references prevent memory leaks

#### Direct Method Calls
- Modules can call public methods on other modules
- App provides getter functions to access module instances
- Used for tight integration when needed

#### Shared State
- Certain state is shared via appState
- Modules subscribe to state changes they care about
- Changes trigger updates in subscribing modules

### Module Initialization Order
1. Core modules (api, utils, toast) - always loaded
2. UI modules (dock, chat) - loaded based on view
3. Feature modules (tasks, calendar, etc.) - loaded when view activates
4. Service modules (background sync, etc.) - always active
5. Utility modules (helpers, formatters) - as needed

## Key Functions

### `init()`
Main application entry point. Called after DOM is ready.
- Sets up event listeners
- Initializes core modules
- Checks backend connectivity
- Loads initial view
- Starts background services

### `destroy()`
Cleanup function called before page unload.
- Saves persistent state
- Cancels ongoing operations
- Destroys all module instances
- Removes event listeners
- Cleans up resources

### `loadView(viewName, options)`
Loads a specific view into the main container.
- Fetches view HTML via AJAX
- Parses and injects into DOM
- Initializes view-specific JavaScript
- Calls view's onload function
- Updates URL and dock state
- Returns promise resolving when view is ready

### `unloadView()`
Unloads the currently loaded view.
- Calls view's onunload function
- Removes view-specific event listeners
- Clears view content from DOM
- Deactivates view-specific modules

### `navigateTo(viewName, options)`
Public method for navigating to a view.
- Updates URL/hash
- Adds to history (unless options.replace)
- Calls loadView with appropriate parameters
- Handles errors and loading states
- Emits navigation events

### `getCurrentView()`
Returns the name of the currently loaded view.

### `isViewLoaded(viewName)`
Checks if a specific view is currently loaded.

### `setAppState(key, value)`
Sets a value in the application state.
- Triggers state change events if value changed
- Persists certain keys to localStorage
- Notifies subscribing modules

### `getAppState(key)`
Retrieves a value from the application state.
- Returns default value if key not found
- Handles nested key access with dot notation

### `onAppStateChange(callback, keys)`
Subscribe to changes in specific state keys.
- Returns unsubscribe function
- Only fires when specified keys actually change
- Handles immediate callback for current value

### `emitEvent(eventName, data)`
Publish an application-wide event.
- Data is cloned to prevent accidental mutation
- Listeners called synchronously
- Errors in listeners caught and logged

### `onEvent(eventName, callback)`
Subscribe to an application-wide event.
- Returns unsubscribe function
- Weak reference to prevent memory leaks
- Callback receives event data

## Background Services

### Connection Monitoring
- Periodically checks backend connectivity
- Updates appState.backendStatus
- Shows/hides connectivity indicators in UI
- Attempts reconnection on failure
- Exponential backoff for reconnect attempts

### State Persistence
- Automatically saves user preferences to localStorage
- Loads persisted state on initialization
- Handles storage quota exceeded gracefully
- Provides API for manual state persistence

### Performance Monitoring
- Tracks view load times
- Monitors API response times
- Logs performance metrics in development
- Provides insights for optimization

## Error Handling

### Global Error Boundaries
- Catches errors in event listeners
- Catches errors in module initialization
- Catches errors in view loading/unloading
- Prevents app from crashing due to unhandled exceptions

### Error Reporting
- Logs errors to console in development
- Optionally sends to error tracking service in production
- Shows user-friendly error messages via toast
- Provides error recovery options (retry, etc.)

### View-Specific Errors
- Each view can handle its own errors
- App provides error display components
- Views can override global error handling
- Error boundaries isolate view failures

## Loading States

### Global Loading Indicator
- Shows spinner during view transitions
- Disables user interaction during loading
- Can be overridden by view-specific loaders
- Configurable duration and appearance

### View Loading States
- Each view can show its own loading indicator
- App provides standard loading components
- Skeleton screens supported for better UX
- Progress indicators for long operations

## URL and History Management

### Hash Change Handling
- Listens to hashchange and popstate events
- Parses new URL and determines target view
- Prevents duplicate navigation to same view
- Handles back/forward navigation correctly

### History Stack
- Maintains internal history stack for advanced navigation
- Supports goBack/goForward with view-specific state
- Allows replacing current entry in history
- Tracks scroll position per view for restoration

### SEO and Shareability
- While primarily SPA, important views have meaningful hash fragments
- Consider implementing pushState for cleaner URLs in future
- Metadata tags updated for social sharing (when implemented)

## Responsive Behavior

### View Adaptation
- Notifies views of breakpoint changes
- Allows views to adapt layout based on screen size
- Provides helper functions for media query matching
- Coordinates responsive dock behavior (vertical/horizontal)

### Window Resize Handling
- Debounced resize event handling
- Updates appState with current dimensions
- Notifies modules of size changes
- Triggers layout recalculations where needed

### Visibility Change Handling
- Handles page visibilitychange event
- Pauses/resumes background activities
- Adjusts update frequencies based on visibility
- Conserves resources when page is hidden

## Accessibility Features

### Focus Management
- Traps focus in modals and dialogs
- Returns focus to triggering element on close
- Manages focus during view transitions
- Ensures logical tab order in dynamically loaded content

### Screen Reader Support
- Updates document title on view change
- Manages ARIA live regions for status updates
- Ensures proper labeling of dynamically generated content
- Provides skip-to-content links

### Keyboard Navigation
- Supports keyboard navigation throughout interface
- Handles escape key for closing dialogs
- Provides shortcuts for common actions (configurable)
- Follows standard keyboard interaction patterns

## Performance Optimizations

### Code Splitting
- Only loads JavaScript for current view
- Uses dynamic import() for page-specific scripts
- Preloads likely next views based on usage patterns
- Minimizes initial payload size

### DOM Efficiency
- Minimizes DOM mutations during view transitions
- Uses document fragments for bulk updates
- Requests animation frame for visual updates
- Avoids layout thrashing

### Event Delegation
- Uses event delegation where possible
- Reduces number of event listeners
- Improves performance for dynamic lists
- Simplifies cleanup when elements removed

### Resource Cleanup
- Properly removes event listeners
- Clears timers and intervals
- Revokes object URLs (for blob URLs)
- Nullifies references to prevent memory leaks

## Debugging and Development Features

### Development Mode
- Enhanced logging when in development
- Performance timers for view loading
- Module initialization tracing
- State change logging
- Network request logging (when enabled)

### Hot Module Replacement (Conceptual)
- Structure supports future HMR implementation
- Modules designed to be safely reloaded
- State preservation during updates
- Quick iteration during development

### Testing Hooks
- Exposes internal methods for testing
- Allows mocking of dependencies
- Provides test IDs for automation
- Supports end-to-end testing scenarios

## Integration with Other Modules

### Dock Module
- Synchronizes dock selection with current view
- Updates dock when URL changes programmatically
- Provides callback for dock item clicks
- Handles responsive dock behavior (vertical/horizontal)

### Chat Module
- Coordinates chat container sizing
- Manages chat input focus during view changes
- Handles chat-specific escape key behavior
- Shares notification system theme and styling variables

### Toast Module
- Provides global notification system
- Used for API errors, successes, warnings
- Configurable positioning and duration
- Supports actionable notifications

### Utility Module
- Provides helper functions used throughout app
- Formatters, validators, DOM helpers
- Consistent utility functions across modules

## Initialization Sequence

1. **DOM Ready**: Wait for DOMContentLoaded event
2. **Core Modules**: Initialize api.js, utils.js, toast.js
3. **State Setup**: Load persisted state from localStorage
4. **Backend Check**: Test connection to backend services
5. **Route Setup**: Configure URL listeners and history
6. **Dock Init**: Initialize navigation dock
7. **Initial View**: Load dashboard or last viewed page
8. **Module Init**: Initialize modules needed for initial view
9. **Event Binding**: Set up global event listeners
10. **Ready Signal**: Emit app-ready event

## Shutdown Sequence

1. **Beforeunload**: Listen for beforeunload event
2. **State Persistence**: Save current state to localStorage
3. **Operation Cancellation**: Cancel ongoing API requests
4. **Module Cleanup**: Call destroy on all modules
5. **Listener Cleanup**: Remove all event listeners
6. **Resource Cleanup**: Clear intervals, timeouts, etc.
7. **Final Save**: Any final state persistence

## Public API

### Methods Accessible to Other Modules
- `navigateTo(viewName)`: Navigate to a view
- `getCurrentView()`: Get current view name
- `isViewLoaded(viewName)`: Check if view is loaded
- `getAppState(key)`: Get application state value
- `setAppState(key, value)`: Set application state value
- `onAppStateChange(callback, keys)`: Subscribe to state changes
- `emitEvent(name, data)`: Emit application event
- `onEvent(name, callback)`: Subscribe to application event
- `getModule(moduleName)`: Get instance of loaded module
- `isBackendOnline()`: Check backend connectivity status
- `showLoading()`: Show global loading indicator
- `hideLoading()`: Hide global loading indicator
- `getViewContainer()`: Get DOM element for view content
- `getDockElement()`: Get DOM element for navigation dock

### Events Emitted by Application
- `app-init`: Fired when application starts initializing
- `app-ready`: Fired when application is fully initialized
- `view-loading`: Fired before view starts loading
- `view-loaded`: Fired when view finishes loading
- `view-unloading`: Fired before view starts unloading
- `view-unloaded`: Fired when view finishes unloading
- `state-change`: Fired when application state changes
- `backend-online`: Fired when backend connection established
- `backend-offline`: Fired when backend connection lost
- `resize`: Fired when window is resized
- `visibility-change`: Fired when page visibility changes
- `keydown:*`: Fired for specific key combinations
- `module-init:*`: Fired when specific module initializes
- `module-destroy:*`: Fired when specific module destroys

## Usage Examples

### From a View Module
```javascript
// In tasks.js or similar view-specific file
export function init() {
  // Subscribe to app events
  const unsubscribe = app.onEvent('app-ready', () => {
    // Initialize when app is ready
    initializeTaskList();
  });
  
  // Subscribe to state changes
  const unsubState = app.onAppStateChange(
    (newVal, oldVal) => {
      if (newVal !== oldVal) {
        // Handle theme change
        updateTheme(newVal);
      }
    },
    ['userPreferences.theme']
  );
  
  // Navigate to another view
  function handleViewDetails(taskId) {
    app.navigateTo('tasks', { 
      query: { id: taskId },
      replace: false 
    });
  }
  
  // Return cleanup function
  return () => {
    unsubscribe();
    unsubState();
  };
}
```

### From a Service Module
```javascript
// In a background sync service
export function startSyncService() {
  // Check backend status periodically
  const checkInterval = setInterval(() => {
    const isOnline = app.isBackendOnline();
    updateSyncStatus(isOnline);
    
    if (!isOnline) {
      // Attempt reconnection
      attemptReconnect();
    }
  }, 30000); // Every 30 seconds
  
  // Respond to app events
  const unsubscribe = app.onEvent('app-ready', () => {
    // Start initial sync when app ready
    performInitialSync();
  });
  
  // Respond to visibility changes
  const unsubscribeVis = app.onEvent('visibility-change', (isVisible) => {
    if (isVisible) {
      // Resume sync when visible
      resumeSync();
    } else {
      // Pause sync when hidden
      pauseSync();
    }
  });
  
  // Return cleanup
  return () => {
    clearInterval(checkInterval);
    unsubscribe();
    unsubscribeVis();
  };
}
```

### From a Utility Function
```javascript
// In utils.js or similar
export function formatDateForDisplay(date) {
  // Get user's preferred format from app state
  const format = app.getAppState('userPreferences.dateFormat') || 'relative';
  
  switch (format) {
    case 'relative':
      return formatRelative(date);
    case 'absolute':
      return formatAbsolute(date);
    case 'iso':
      return date.toISOString();
    default:
      return formatRelative(date);
  }
}
```

## Error Boundaries and Recovery

### View Loading Errors
When a view fails to load:
1. Show error message in view container
2. Provide retry button
3. Log error details
4. Optionally load fallback view
5. Emit view-load-error event

### Module Initialization Errors
When a module fails to initialize:
1. Log error with module name
2. Mark module as failed in appState
3. Continue loading other modules
4. Provide degraded functionality if possible
5. Emit module-init-error event

### Runtime Errors
When errors occur during execution:
1. Catch in try/catch or event listener wrapper
2. Log error with context (view, module, action)
3. Show user-friendly message if appropriate
4. Offer recovery options (reload, retry, etc.)
5. Emit appropriate error event

## State Persistence

### Automatically Persisted State
- User preferences (theme, date format, etc.)
- View-specific states (scroll positions, filter states, etc.)
- Window dimensions and positions (for resizable panels)
- Recently viewed items
- Backend connection history

### Storage Mechanism
- Uses localStorage for persistence
- JSON serialization with versioning
- Handles storage quota errors gracefully
- Provides migration mechanisms for schema changes

### State Structure
```javascript
{
  version: 1,
  userPreferences: {
    theme: 'light',
    dateFormat: 'relative',
    showAnimations: true,
    compactMode: false
  },
  viewStates: {
    tasks: {
      sortBy: 'dueDate',
      filter: 'pending',
      scrollPosition: 0
    },
    calendar: {
      currentMonth: '2026-07',
      viewType: 'month'
    }
    // ... other views
  },
  windowState: {
    width: 1280,
    height: 720,
    sidebarCollapsed: false
  },
  history: [
    '/dashboard',
    '/tasks',
    '/calendar'
  ],
  backend: {
    lastKnownOnline: true,
    reconnectAttempts: 0
  }
}
```

## Performance Considerations

### Initial Load Time
- Core modules loaded immediately
- View-specific modules lazy-loaded
- Critical CSS inlined for above-the-fold content
- Font loading optimized with font-display: swap
- Images lazy-loaded where appropriate

### Runtime Performance
- Minimizes layout thrashing with read/write separation
- Uses requestAnimationFrame for animations
- Debounces frequent events (resize, scroll)
- Throttles API calls where appropriate
- Virtual scrolling for long lists (in relevant views)

### Memory Usage
- Properly cleans up event listeners and timers
- Weak references for event subscriptions
- Object pooling for frequently created/destroyed items
- Efficient data structures for state management
- Periodic garbage collection hints

### Network Efficiency
- Request deduplication prevents duplicate calls
- Caching of GET requests where appropriate
- Compression of large payloads
- Batching of related operations
- Adaptive polling based on activity

## Accessibility Compliance

### WCAG 2.1 AA Guidelines
- Perceivable: Text alternatives, adaptable content, distinguishable
- Operable: Keyboard accessible, enough time, seizure prevention
- Understandable: Readable, predictable, input assistance
- Robust: Compatible with current and future user agents

### Specific Implementation
- **Keyboard Navigation**: All interactive elements accessible via keyboard
- **Focus Order**: Logical tab order maintained in dynamic content
- **Focus Visible**: Clear focus indicators on all interactive elements
- **ARIA Labels**: Proper labeling for icons, buttons, and dynamic content
- **Live Regions**: Status updates announced to screen readers
- **Color Contrast**: Text and UI elements meet contrast ratios
- **Resizable Text**: Content scales properly up to 200% zoom
- **Touch Targets**: Minimum 44x44px for touch interactions
- **Reduced Motion**: Animations respect user preferences
- **Screen Reader Testing**: Regular testing with common screen readers

## Security Considerations

### XSS Prevention
- All dynamic content properly escaped
- Uses textContent instead of innerHTML where possible
- When innerHTML necessary, uses DOMPurify or similar
- JSON parsing done securely with reviver functions
- Template literals avoided for user-generated content

### CSRF Protection
- Relies on SameSite cookies for session management
- POST/PUT/DELETE requests originate from same origin
- No sensitive actions可通过 simple GET requests
- Tokens would be added if backend authentication implemented

### Data Protection
- No sensitive data stored in URL
- LocalStorage used judiciously for non-sensitive preferences
- Backend handles encryption of sensitive data at rest
- Frontend follows principle of least privilege for data access

### Content Security Policy
- Ready to support CSP headers
- No inline scripts or styles (all external)
- Eval() and similar functions avoided
- Base URI properly restricted

## Dependencies

### Internal Dependencies
- `api.js`: For all backend communications
- `utils.js`: For helper functions
- `toast.js`: For user notifications
- `dock.js`: For navigation (though could be considered peer)
- `chat.js`: For chat interface coordination

### External Dependencies
- None (uses only native browser APIs)
- Designed to work without external libraries
- Easy to integrate with frameworks if needed in future
- Polyfill strategy documented for older browsers

### Browser Support Matrix
| Feature | Chrome | Firefox | Safari | Edge | Mobile |
|---------|--------|---------|--------|------|--------|
| Core App | ✓ | ✓ | ✓ | ✓ | ✓ |
| History API | ✓ | ✓ | ✓ | ✓ | ✓ |
| Fetch API | ✓ | ✓ | ✓ | ✓ | ✓ |
| AbortController | ✓ | ✓ | ✓ | ✓ | ✓ |
| Promises | ✓ | ✓ | ✓ | ✓ | ✓ |
| Class Syntax | ✓ | ✓ | ✓ | ✓ | ✓ |
| Arrow Functions | ✓ | ✓ | ✓ | ✓ | ✓ |
| Let/Const | ✓ | ✓ | ✓ | ✓ | ✓ |
| Template Literals | ✓ | ✓ | ✓ | ✓ | ✓ |
| Destructuring | ✓ | ✓ | ✓ | ✓ | ✓ |
| Modules (ESM) | ✓ | ✓ | ✓ | ✓ | ✓ |
| LocalStorage | ✓ | ✓ | ✓ | ✓ | ✓ |
| SessionStorage | ✓ | ✓ | ✓ | ✓ | ✓ |

## Implementation Notes

### Coding Style
- Uses modern ES6+ syntax (classes, arrow functions, destructuring)
- Follows consistent naming conventions (camelCase for variables/functions)
- Modules use IIFE or ES modules pattern
- Constants in UPPER_SNAKE_CASE
- Private methods prefixed with underscore
- JSDoc comments for public APIs
- Maximum line length 100 characters
- 2-space indentation
- Trailing commas in multi-line lists

### File Organization
- Single responsibility: app coordination only
- View-specific logic kept in view modules
- Business logic in services or utils
- UI manipulation minimized (delegated to view modules)
- State changes centralized in appState

### Error Handling Philosophy
- Fail fast during development
- Graceful degradation in production
- User-friendly error messages
- Recovery options provided when possible
- Errors logged appropriately for debugging

### Testing Approach
- Unit testable through dependency injection
- Integration tests for view loading/navigation
- End-to-end tests for user flows
- Mock backend for consistent testing
- Performance benchmarks for critical paths

## Future Enhancements

### Advanced Routing
- PushState support for cleaner URLs
- Nested routes for complex views
- Route parameters and query string parsing
- Route guards for authentication/protection
- Lazy loading of route-based code bundles

### State Management Evolution
- Migration to Redux/Zustand/etc. for complex state
- Time-travel debugging for state changes
- State persistence middleware
- Optimistic updates for better UX
- Selectors for derived state

### Plugin Architecture
- Formal plugin system for extensibility
- Plugin lifecycle hooks
- Sandboxed plugin execution
- Marketplace for community plugins

### Developer Experience
- Improved logging and debugging tools
- Performance profiling integration
- Component isolation testing
- Storybook integration for UI components
- TypeScript definitions and support

### Mobile-Specific Features
- Touch gesture support (swipe navigation)
- Native feeling transitions
- Offline-first capabilities
- Progressive Web App (PWA) features
- Deep linking and app links support

### Accessibility Improvements
- Enhanced screen reader support
- Better keyboard navigation patterns
- Voice control compatibility
- High contrast mode support
- Internationalization and localization support