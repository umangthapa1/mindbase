# Frontend JavaScript

This directory contains JavaScript files for the frontend.

## Files

- `api.js` - Wrapper for backend API requests and service orchestration
- `app.js` - Main application entrypoint, initialization, and routing
- `chat.js` - Chat interface logic, context menu actions, and exporting conversations to `.txt` files
- `dock.js` - Navigation dock/sidebar construction and state synchronization
- `email.js` - Email client interface and message viewer logic
- `theme.js` - System theme loader and selector utilities
- `toast.js` - Toast notifications system for feedback
- `utils.js` - Common helper functions, markdown rendering parser, and DOM selector shortcuts (`$` and `$$`)

## Conventions

- No build step - files are served as-is.
- Use vanilla JavaScript (no frameworks).
- Keep functions small and focused.
- Avoid global variables; use modules or IIFE where appropriate.
