# `frontend/pages/page-theme.css`

Shared layout styles for Mindbase sub-pages. It is loaded after `frontend/css/globals.css`.

## Responsibilities

- Offset page content for the fixed application dock.
- Provide sticky page headers, responsive content widths, cards, grids, forms, and section labels.
- Define shared page-level controls such as field labels, buttons, tables, and empty states.
- Collapse the dock offset and grids for smaller screens.

Sub-pages should use the shared variables from `globals.css` instead of introducing isolated theme colors. The stylesheet expects `dock.js` to add `has-app-dock` and related dock classes to the page.
