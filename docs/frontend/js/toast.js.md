# toast.js

Frontend toast notification system for displaying temporary messages.

## Purpose

This file implements a lightweight notification system that displays temporary messages (toasts) to the user, such as:
- Success messages (e.g., "Task created successfully")
- Error messages (e.g., "Failed to send email")
- Warning messages (e.g., "Unsaved changes")
- Informational messages (e.g., "Syncing with server")

## Contents

- Toast container creation and management
- Toast rendering and animation (fade-in/slide-out)
- Toast queueing system (to prevent multiple toasts from overlapping)
- Configuration options (duration, position, styling)
- Methods for adding different types of toasts (success, error, warning, info)
- Automatic cleanup of expired toasts

## Usage

The toast system is initialized in `app.js` and can be used throughout the application by calling:
```javascript
toast.success("Message");
toast.error("Message");
toast.warning("Message");
toast.info("Message");
```
