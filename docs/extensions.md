# Declarative extension packs — Phase 4

Phase 4 adds a controlled extension-pack boundary. An extension can contribute validated
workflow plans and declarative component templates, request explicit existing capability
permissions, be enabled/disabled, and roll back to an immutable release. It cannot install or
execute arbitrary code.

## Security boundary

An extension manifest is data only. The schema rejects unknown fields such as `entrypoint`,
`module`, `code`, `script`, URLs, shell commands, and model-generated function bodies. It may
contain only:

- metadata (`id`, `name`, description, schema version);
- an allowlisted permission list;
- Phase 3 declarative templates;
- Phase 2 validated workflow plans.

The existing capability permission vocabulary is reused (`tasks.write`, `calendar.write`,
`reminders.write`, `notifications.write`, `workflows.write`, and corresponding reads). A
template's permissions must be declared by its pack. A workflow's required permissions are
derived from its steps and must also be declared. Installation requires a separate explicit
`grant_permissions` list containing every requested permission; manifest declaration alone is
not consent.

There is no extension execution engine, dynamic import, plugin process, arbitrary function hook,
network permission, filesystem permission, or subprocess permission in Phase 4. A pack can ask
the existing bounded runtime to execute a validated workflow, but it cannot add a new handler.
This is intentional; new executable capability generation belongs to the later proposal phase.

## Manifest example

```json
{
  "schema_version": 1,
  "id": "care-pack",
  "name": "Care pack",
  "description": "Local care workflows and status panels",
  "permissions": [
    "workflows.read", "workflows.write", "tasks.write",
    "reminders.read", "reminders.write"
  ],
  "templates": [
    {
      "id": "care-panel",
      "name": "Care panel",
      "definition": {
        "schema_version": 1,
        "layout": "stack",
        "permissions": ["workflows.read"],
        "nodes": [
          {"id": "title", "type": "text", "source": "title"},
          {"id": "status", "type": "status", "source": "status"}
        ],
        "actions": []
      }
    }
  ],
  "workflows": [
    {
      "id": "stretch",
      "name": "Stretch reminder",
      "plan": {
        "title": "Stretch",
        "steps": [
          {"id": "reminder", "action": "create_reminder",
           "inputs": {"label": "Stretch", "duration_seconds": 60}}
        ]
      }
    }
  ]
}
```

Install it with:

```http
POST /api/workspace/extensions
Content-Type: application/json

{
  "manifest": { "...": "the validated manifest above" },
  "grant_permissions": [
    "workflows.read", "workflows.write", "tasks.write",
    "reminders.read", "reminders.write"
  ]
}
```

The Settings page provides a local JSON manifest editor and a comma-separated grant field.
The server remains authoritative; the browser editor does not bypass validation.

## Releases and rollback

Every installed pack starts at release version 1. `POST /api/workspace/extensions/{id}/versions`
adds an immutable release. Its manifest ID must match the installed extension. New permissions
must be explicitly included in `grant_permissions`; previously granted permissions are retained
until the extension is uninstalled. Each release stores a SHA-256 digest of the canonical JSON
manifest for auditability.

Extension templates are materialized into the Phase 3 template registry under a namespaced ID
such as `extension--care-pack--care-panel`. Each release creates a new immutable template version,
even when the definition is unchanged. Existing component instances stay pinned to their old
template version. New instances use the active release's current version.

Rollback selects an existing release and materializes its definitions as another immutable
template version. It does not rewrite or invalidate existing instances. Removed templates are
archived while their old versions remain readable by pinned components.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/workspace/extensions` | Install a pack with explicit grants |
| `GET /api/workspace/extensions` | List installed packs and active release summaries |
| `GET /api/workspace/extensions/{id}` | Read manifest, releases, permissions, and audit history |
| `POST /api/workspace/extensions/{id}/versions` | Add and activate an immutable release |
| `POST /api/workspace/extensions/{id}/actions` | `enable`, `disable`, `rollback` with `version`, or `uninstall` |
| `POST /api/workspace/extensions/{id}/workflows/{key}/runs` | Run an active validated workflow pack entry |

Disabling archives pack-owned templates and blocks new workflow runs/instances. Existing
workflow executions and pinned panels continue to operate. Enabling restores only templates
present in the active manifest. Uninstalling is terminal: it archives pack-owned templates,
keeps old instances readable, and blocks enable, release, and workflow-run actions.

All lifecycle changes create an audit row containing the action, version, digest or safe detail,
and timestamp. No manifest secrets are accepted by the schema. The extension registry and audit
history survive backend restarts; workspace reset leaves installed extension definitions as
configuration while removing runtime component/workflow instances.

## Failure and persistence guarantees

- Manifest validation and permission checks happen before extension rows or templates are written.
- Installation, release materialization, active-version changes, and audit records commit as one
  transaction.
- Template versions are immutable and component pins survive release updates and rollback.
- Extension status and active release survive restart.
- Repeated enable/disable actions are safe; installing an existing ID returns HTTP 409.
- Running a disabled/uninstalled extension returns HTTP 409; missing packs/workflows return 404.
- New workflow runs use the existing Phase 2 idempotency key mechanism. A supplied key is scoped
  to extension ID, release version, and workflow key, preventing duplicate artifacts after a
  retried HTTP request.
- Permission revocation is represented by disable/uninstall in Phase 4. A future policy UI can
  add granular grant removal after defining how existing executions should behave.

## What this phase does not do

Phase 4 does not generate Python, JavaScript, SQL, browser extensions, new runtime handlers, or
system integrations. It provides a safe package boundary for declarative composition over
existing capability handlers. Phase 5 may propose new capabilities, but proposals must still
be evaluated, tested, approved, sandboxed, and rollback-capable before installation.

## Verification

```sh
venv/bin/python backend/tests/run_isolated.py -q backend/tests/ --tb=short --disable-warnings
node --test frontend/tests/*.test.cjs
```

The Phase 4 backend tests cover permission grants, rejection of executable manifest fields,
namespaced template materialization, idempotent workflow runs, disable/enable behavior, pinned
release updates, rollback, uninstall, audit records, and reopen persistence. Frontend tests cover
the Settings manifest/grant controls and encoded extension API requests. The full Firefox runtime
suite continues to verify Phase 1–3 UI behavior; extension lifecycle controls are also available
from Settings.
