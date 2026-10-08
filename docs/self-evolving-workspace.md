# Workspace runtime — Phases 1 and 2

Phase 1 adds a persistent capability foundation and a controlled reminder widget to the
existing local workspace. Its plans and components are validated data. The handlers
and renderers are developer-defined; the application does not generate or execute new code.

Phase 2 adds **durable multi-step workflows** over the task, calendar, reminder, and notification
handlers. See [Workflow planning and execution](workflows.md) for schemas, lifecycle, retries,
linked completion, examples, and delivery guarantees.

Phase 3 adds [versioned declarative workspace components](components.md). Workflow panels and
custom instances use immutable, allowlisted JSON templates with safe text/progress/list rendering,
explicit lifecycle actions, and pinned upgrades. Template data cannot execute code.

Phase 4 adds [declarative extension packs](extensions.md). Packs can compose existing capabilities
with explicit grants, immutable releases, audit history, enable/disable, and rollback. They still
cannot add or execute arbitrary code.

## Try it

Start Mindbase normally, open chat, and send:

> remind me to check on grandpa in 30 seconds

This creates a **Check on grandpa** countdown and an in-app notification, without creating
a task or contacting a model. Seconds (`s`, `sec`, `secs`), minutes, hours, and compound
durations work, including `can u remind me to stretch in like 15 mins` and
`set a timer for 1 minute`. Labels are limited to 200 characters and delays to
1 second–365 days (expressed in seconds/minutes/hours).

Absolute times, dates, recurring schedules, fractional durations, and unrecognized
timing formulations ask for clarification. A timing answer such as `in 30 seconds`
can resume a clear pending reminder request; unclear labels require a restatement.
Existing `add task: ...` requests and calendar commands retain their existing handlers.

## Persistence and lifecycle

- SQLite owns reminder state, component visibility/order, events, and notification delivery.
  New tables are added with `create_all`; existing workspace tables and data are retained.
- Active deadlines use UTC, serialized with `Z`. The browser draws a countdown from the
  deadline, rather than decrementing a stored number or creating its own scheduler.
- **Pause** stores the actual remaining duration, including fractions of a second.
  **Resume** sets a new deadline. Component props derive from the same reminder record.
- **Done** and **Cancel** are terminal states. Repeated matching actions are idempotent;
  invalid transitions return HTTP 409. Finishing/cancelling suppresses pending alerts.
- A backend worker checks deadlines every second. A conditional row update claims a
  due reminder and writes one notification and `reminder.due` event in the same transaction.
  A unique reminder/notification constraint and durable status prevent duplicate creation.
- When the backend restarts, overdue active reminders become due. Paused reminders stay paused.
- Widgets are global to this local workspace. Move earlier/later changes durable ordering.
  Closing hides the widget **while the reminder keeps running**; “Closed widgets” restores it.
  Buttons support keyboard focus and labelled actions. Countdown ticks are not live-announced.
- Positive chat completion acknowledgements can complete one exact latest reminder in that
  conversation. Duplicate labels, mismatched activities, and ambiguous references do not guess.
- Workspace reset deletes runtime content in foreign-key order and retains the core registry.

## Notification delivery guarantees

Notification GETs are **non-consuming**. The visible chat page mounts a text-only toast,
waits for a render frame, then explicitly acknowledges its ID. Hidden documents do not
consume notifications. Failed acknowledgements retry without another toast in the same page;
failed rendering leaves the alert pending. Poll failures preserve the last known widgets.

Delivery is **at least once**, not exactly once: a crash between display and acknowledgement,
or multiple open chat tabs, may show the same alert again. Due notifications remain in SQLite
until acknowledged or the reminder is completed/cancelled. The notification API returns up
to 100 pending records per poll.

The backend must be running to process a deadline. If stopped, overdue reminders are recovered
on restart. In-app alerts are delivered when a visible **chat page** is open; closing the
browser or browsing only secondary pages defers them until chat is reopened. Phase 1 does not
provide OS notifications, push delivery, or a system service that runs while Mindbase is stopped.

## Modules and API

- `backend/capabilities.py`: idempotently seeds tasks, calendar, timer, notifications, memory,
  and workflows. Timer/notification enable choices survive restart and gate new reminder
  creation; workflow enable choices gate new workflow creation. Existing reminders and
  workflows continue running and remain manageable. A disabled timer/notification handler
  causes its new workflow steps to fail and follow the bounded retry policy. Other registry
  entries catalog existing handlers; their enable/disable API is not available.
- `backend/workspace_planner.py`: validates explicit requests into `intent`, `capability_id`,
  `inputs`, `confidence`, and `explanation`, sent in chat SSE `meta.plan`.
- `backend/workspace_runtime.py`: typed API, reminder lifecycle, event log, and scheduler.
- `backend/component_runtime.py`: strict template schemas, immutable versions, instance lifecycle,
  built-in workflow template, and template/component APIs.
- `frontend/js/workspace-runtime.js`: allowlisted JSON renderer, countdowns, persistent controls,
  declarative panels, polling, and notification acknowledgements. No `eval`, generated HTML, or
  generated scripts.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/capabilities` | Read core registry |
| `PATCH /api/capabilities/{id}` | Set timer/notifications/workflows `{"enabled": false}` |
| `GET /api/workspace/components` | Read visible and closed widgets with current props |
| `PATCH /api/workspace/components/{id}` | Set `{"visible": false}` or `{"move": "earlier"}` / `"later"` |
| `POST /api/workspace/reminders` | Create `{"label": "Stretch", "duration_seconds": 30}` |
| `GET /api/workspace/reminders` | Read reminder lifecycle state |
| `POST /api/workspace/reminders/{id}/actions` | `{"action": "pause"}` / `"resume"` / `"complete"` / `"cancel"` |
| `GET /api/workspace/events` | Read the most recent 100 runtime events |
| `GET /api/workspace/notifications` | Read up to 100 pending alerts without consuming them |
| `POST /api/workspace/notifications/{id}/ack` | Idempotently acknowledge display |
| `GET /api/workspace/templates` | List versioned declarative templates |
| `POST /api/workspace/templates` | Create a validated template version 1 |
| `POST /api/workspace/templates/{id}/versions` | Append an immutable template version |
| `POST /api/workspace/templates/{id}/instances` | Create a pinned component instance |
| `POST /api/workspace/components/{id}/actions` | Archive, restore, or upgrade a component |

Only these bounded mutations are exposed. Permission names in the core registry document
handler scope; they are not a sandbox for plugins or an arbitrary-code permission system.
This retains the application's existing local, single-user trust model.

## Verification

Run from the repository root:

```sh
venv/bin/python backend/tests/run_isolated.py -q backend/tests/ --tb=short --disable-warnings
node --test frontend/tests/*.test.cjs
```

The backend runner uses copied source, disposable storage, stub embeddings, and blocked
network access. Runtime API regressions cover timing validation, exact completion references,
pause/resume, durable notifications, reset, component controls, and SQLite reopen recovery.

The Firefox test starts a real backend in `/tmp/omnirush`, with disposable browser and database
profiles, model/mail services stubbed, and external browser traffic blocked. It exercises the
actual chat and runtime scripts: the full 30-second countdown/alert, pause and reload, resume,
multiple short reminders, acknowledgements, persistent move/close/restore, mobile layout, and
actual server restarts. Phase 2 also exercises a failed workflow surviving restart, UI retry,
linked task completion, UI cancellation, and deferred task creation across two more restarts.
Phase 3 verifies a safe custom panel, progress/list nodes, version upgrade, archive, and restore.
No live workspace data or credentials are copied. Firefox and the
project Python environment are needed for this test; `FIREFOX_BIN` and `MINDBASE_TEST_PYTHON`
can override their paths.

## Later phases

1. **Phase 1 — implemented:** controlled registry, validated reminder plans, persistent runtime and UI.
2. **Phase 2 — implemented:** validated multi-step workflows over existing capabilities, durable execution state,
   bounded retries, linked completion, and workflow status controls.
3. **Phase 3 — implemented:** composable declarative components, immutable template versions,
   pinned instances, safe rendering, and lifecycle management.
4. **Phase 4 — implemented:** declarative extension packs with explicit permission grants,
   immutable releases, audit history, isolation by non-execution, and rollback.
5. **Phase 5:** feedback-driven proposals, evaluation, and controlled capability evolution.

Phase 5 remains separate implementation work. It is the phase that could propose new capabilities;
it is not enabled by the declarative extension pack system.
