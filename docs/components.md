# Declarative workspace components — Phase 3

Phase 3 provides a reusable, versioned presentation layer for workflows and local workspace
data. A component is an instance of an immutable template version. Templates contain only
allowlisted JSON nodes and actions; they cannot contain HTML, JavaScript, CSS, SQL, shell
commands, model prompts, or executable expressions.

## Built-in workflow panel

Every new workflow receives the pinned `workflow-status` template version 1. Its panel uses:

- a text node for the workflow title;
- a status node for the lifecycle state;
- a progress node for completed/total steps;
- a list node for each step and its status/error;
- allowlisted `retry` and `cancel` actions requiring `workflows.write`.

Existing workflow instances remain compatible. Instances created before the Phase 3 migration
continue using their legacy workflow renderer until explicitly upgraded or recreated; their
execution state is unaffected.

## Template schema

Create a template with `POST /api/workspace/templates`:

```json
{
  "id": "care-panel",
  "name": "Care panel",
  "description": "A local care status panel",
  "definition": {
    "schema_version": 1,
    "layout": "stack",
    "permissions": ["workflows.read", "workflows.write"],
    "nodes": [
      {"id": "title", "type": "text", "source": "title"},
      {"id": "status", "type": "status", "source": "status"},
      {"id": "progress", "type": "progress", "source": "progress"},
      {"id": "steps", "type": "list", "source": "steps"}
    ],
    "actions": [
      {"id": "cancel", "label": "Cancel", "action": "cancel", "permission": "workflows.write"}
    ]
  }
}
```

The supported node types are `text`, `status`, `progress`, and `list`. Sources are limited to
`title`, `label`, `status`, `message`, `steps`, `completed_steps`, `total_steps`, and `progress`.
Lists bind only to workflow steps; progress nodes bind only to `progress`. Actions are limited
to `retry`, `cancel`, `pause`, `resume`, and `complete`. A template can declare read/write
permissions from the existing local capability vocabulary, and every action permission must
be declared by its template.

Definitions are limited to 16 KiB, with up to 12 nodes and 8 actions. IDs are lowercase
identifier keys. Unknown fields, unknown node/source/action types, duplicate IDs, undeclared
permissions, and arbitrary action permissions return HTTP 422 before any database mutation.
Component instance data is JSON text data limited to 12 KiB. The frontend uses `textContent`,
DOM progress elements, and DOM list nodes; data such as `<img onerror=...>` remains literal text.

## Versions and instances

`POST /api/workspace/templates/{id}/versions` appends an immutable version and advances the
template's current version. Existing instances keep their `template_version`. New instances
pin the current version unless `template_version` is explicitly supplied. This makes a
template update safe for currently running workflows.

`POST /api/workspace/templates/{id}/instances` accepts:

```json
{
  "template_version": 1,
  "title": "Optional display title",
  "data": {
    "title": "Grandpa care",
    "status": "active",
    "progress": 0.5,
    "steps": [{"action": "call", "status": "pending"}]
  },
  "workflow_id": "optional-existing-workflow-id"
}
```

Instances can upgrade explicitly with `POST /api/workspace/components/{id}/actions` and
`{"action":"upgrade"}`. Upgrade changes only the pinned template version; it never mutates
the instance's data. If a newer version changes its node layout, the next poll renders the
new layout against the same data. A template's version history remains available through
`GET /api/workspace/templates/{id}`.

Template status can be set with `PATCH /api/workspace/templates/{id}` and
`{"status":"archived"}` or `{"status":"active"}`. Archived templates retain all versions
and existing instances but cannot receive new versions or create new instances.

## Component lifecycle

Component actions:

| Action | Effect |
| --- | --- |
| `archive` | Marks the component archived and hides it; its linked workflow/reminder continues running |
| `restore` | Makes an archived component active and visible |
| `upgrade` | Pins the component to its template's current version |
| `close` / `show` | Existing visibility-only controls; closing does not stop execution |
| `earlier` / `later` | Existing durable ordering controls |

Archived and closed components appear in the accessible “Closed widgets” group. Restore buttons
are keyboard-focusable. Workflow panels retain retry/cancel controls, and custom panels render
only the actions declared by their template. Poll refreshes preserve focus and never execute
template data.

The existing `workspace_components` table gains nullable template/version fields and a lifecycle
field through an idempotent SQLite migration. Old rows default to active lifecycle and remain
visible. New template/version tables are created with `create_all`; template seeding is
idempotent. Workspace reset removes component instances with the runtime content while retaining
the built-in template registry and its immutable version history.

## API summary

| Endpoint | Purpose |
| --- | --- |
| `GET /api/workspace/templates` | List templates and current versions |
| `POST /api/workspace/templates` | Create version 1 |
| `GET /api/workspace/templates/{id}` | Read full immutable version history |
| `PATCH /api/workspace/templates/{id}` | Archive/activate a template |
| `POST /api/workspace/templates/{id}/versions` | Append an immutable version |
| `POST /api/workspace/templates/{id}/instances` | Create a pinned component instance |
| `POST /api/workspace/components/{id}/actions` | Archive, restore, or upgrade an instance |
| `GET /api/workspace/components` | Read instances with live props and template definitions |

The existing workflow, reminder, notification, move, and close endpoints remain unchanged.
The component endpoint exposes definitions to the trusted local browser, but all values are
validated server-side and treated as text by the renderer.

## Guarantees and boundaries

- Template versions are immutable and instances are pinned until an explicit upgrade.
- Archive/restore and ordering survive reload and backend restart.
- Workflow execution is independent of panel visibility or template version.
- Component actions are allowlisted; no arbitrary endpoint, function, or capability name can be
  supplied through a definition.
- Declarative nodes are presentation only. They do not create tasks, send mail, run code, or
  change workflow state unless a declared action maps to an existing bounded handler.
- Phase 3 does not generate templates autonomously or learn new capabilities. Phase 4 would
  need separate sandboxing and permission isolation for extensions; Phase 5 would add controlled
  feedback-driven proposals.

## Verification

```sh
venv/bin/python backend/tests/run_isolated.py -q backend/tests/ --tb=short --disable-warnings
node --test frontend/tests/*.test.cjs
```

The Phase 3 backend suite covers strict schema rejection, built-in seeding, version immutability,
pinned instances, safe data, template archive/activation, component archive/restore/upgrade,
bounded instance data, reopen persistence, and workflow integration. The frontend suite covers
text-only rendering, progress/list output, action allowlisting, and lifecycle API routing. The
real Firefox suite verifies a versioned panel, safe text display, progress/list rendering,
upgrade, archive, restore, mobile layout, and persistence alongside Phase 1 and Phase 2 flows.
