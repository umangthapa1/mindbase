# email.js

Frontend email module for handling email composition, reading, and management.

## Purpose

This file implements the email user interface and interactions, including:
- Displaying email lists and individual emails
- Composing and sending new emails
- Reading and viewing email contents
- Managing email folders (inbox, sent, drafts, etc.)
- Handling email attachments
- Searching and filtering emails

## Contents

- Email list rendering and interaction handlers
- Email composition form and sending logic
- Email reading pane and display utilities
- Folder navigation and management
- Attachment handling and preview
- Search and filter functionality
- Integration with backend email service via API.js

## Usage

The email module is initialized in `app.js` and provides the email interface accessible from the navigation or dock. It communicates with the backend through the `api.js` module for sending, receiving, and managing emails.
