# Frontend Documentation

Reference pages for the no-build HTML, CSS, and JavaScript frontend.

## Application

- [`index.html`](./index.html.md) - Main chat shell and workspace navigation
- [`pages/`](./pages/) - Dashboard, notes, tasks, email, documents, automations, settings, and other views

## JavaScript

- [`js/api.js`](./js/api.js.md) - Backend request and streaming client
- [`js/app.js`](./js/app.js.md) - Application shell and view lifecycle
- [`js/chat.js`](./js/chat.js.md) - Conversations, streaming replies, and message actions
- [`js/dock.js`](./js/dock.js.md) - Shared navigation dock
- [`js/email.js`](./js/email.js.md) - Email view behavior
- [`js/toast.js`](./js/toast.js.md) - Toasts and confirmation dialogs
- [`js/utils.js`](./js/utils.js.md) - Shared browser utilities
- [`js/theme.js`](./js/theme.js.md) - Theme and background-pattern persistence
- [`js/accent.js`](./js/accent.js.md) - Accent presets, custom colors, and contrast variants

## CSS and assets

- [`css/globals.css`](./css/globals.css.md) - Design tokens and shared application styles
- [`css/page-theme.css`](./css/page-theme.css.md) - Legacy/shared page style reference
- [`pages/page-theme.css`](./pages/page-theme.css.md) - Active sub-page layout stylesheet
- [`assets/`](./assets/) - Frontend asset notes

The frontend has no build step. Changes are served directly by the FastAPI application.
