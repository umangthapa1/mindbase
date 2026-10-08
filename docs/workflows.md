# Workflow planning and execution — Phase 2

Workflows compose validated local capabilities into persistent execution plans. The current
handlers create tasks, calendar events, reminders, and notifications, or wait for a reminder
deadline/completion. Plans can be read back and reused with a fresh submission key.

## Chat examples

> Create a task to call grandpa tomorrow and remind me in 30 minutes

This creates a task with tomorrow's due date and a separate 30-minute reminder. The records
are linked by IDs, and the workflow waits for completion. Completing the task through the
Tasks API/page or completing the reminder through its Done button completes both and
suppresses any undelivered reminder alert. A matching positive chat acknowledgement such
as `I called grandpa` also completes the exact latest linked task. Duplicate workflow titles,
multiple linked tasks, or mismatched activities require an explicit widget action.

> Remind me to stretch in 5 seconds then create task: Drink water tomorrow

Here `then` creates a dependency on the reminder's deadline. The follow-up task is created
when the reminder becomes due, including after a backend restart. It does not depend on
whether the browser displayed the alert. A reminder completed early also satisfies this wait.

> Create task: Buy milk and notify me that the task was created

This creates the task and queues an in-app notification using the same explicit display
acknowledgement protocol as reminders.

Chat supports explicit `add/create task`, `remind me`, `set a timer`, and `notify/tell me`
clauses joined with `and`, `then`, or `and then`. Task/pronoun reminder combinations link
automatically; an explicitly different reminder label stays independent. `then` after a
reminder waits for its deadline before a task/notification step. Compound durations such as
`1 hour and 2 minutes` remain one timing expression.

Unrecognized steps or ambiguous timing ask a question **before creating any workflow or
artifact**. A clear pending timing question accepts `in 30 seconds` and resumes the entire
plan. More complex requests can be expressed with the typed API; calendar workflow steps
currently require explicit start/end dates through that API.

## Typed API

`POST /api/workspace/workflows` accepts a plan and an optional `idempotency_key`:

```json
{
  "idempotency_key": "one-stable-key-for-this-request",
  "plan": {
    "title": "Call grandpa",
    "steps": [
      {
        "id": "task",
        "action": "create_task",
        "inputs": {"title": "Call grandpa", "due_date": "2026-10-07T09:00:00"}
      },
      {
        "id": "reminder",
        "action": "create_reminder",
        "depends_on": ["task"],
        "inputs": {"label": "Call grandpa", "duration_seconds": 1800, "task_step_id": "task"}
      },
      {
        "id": "done",
        "action": "wait_for_reminder",
        "depends_on": ["reminder"],
        "inputs": {"reminder_step_id": "reminder", "until": "completed"}
      }
    ]
  }
}
```

| Action | Inputs |
| --- | --- |
| `create_task` | `title`; optional `description`, `priority`, `status`, `due_date`, `tags` |
| `create_calendar_event` | `title`, `start_at`, `end_at`; optional `description`, `location`, `all_day` |
| `create_reminder` | `label`, integer `duration_seconds`; optional `task_step_id` |
| `wait_for_reminder` | `reminder_step_id`; `until` is `due` (default) or `completed` |
| `notify` | Text `message` |

Plans contain 1–20 steps in topological order. IDs are unique, start with a lowercase letter,
and contain lowercase letters/digits/underscores/hyphens (maximum 40 characters). Dependencies
must refer to earlier steps. Linked references must also be direct dependencies of the correct
action type. Cycles, unknown actions, extra fields, invalid dates, empty labels, and invalid
durations return HTTP 422 before execution. Calendar end must follow start.

Task/calendar dates retain the application's local-time storage convention. ISO timestamps
with offsets are converted to server-local time; reminder deadlines use UTC. Natural task
dates are resolved when planning and stored as absolute dates, so a restart does not shift
"tomorrow". Reusing an old plan retains its recorded dates; submit a new request to replan them.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/workspace/workflows` | Validate, persist, and start a plan |
| `GET /api/workspace/workflows` | List up to 100 recent workflows, including plans and results |
| `GET /api/workspace/workflows/{id}` | Read one workflow and each step's state, attempts, error, and result |
| `POST /api/workspace/workflows/{id}/actions` | `{"action": "retry"}` or `{"action": "cancel"}` |

Repeated submissions with the same key and normalized plan return the same workflow. Reusing
that key with a different plan returns HTTP 409. Use the same key when retrying an uncertain
HTTP submission; use a fresh key for a deliberate new run. The chat endpoint creates a new
workflow for each new chat request. It does not deduplicate deliberately repeated messages.

## Execution and recovery

- `workflows` stores the immutable validated plan and overall state. `workflow_steps` stores
  individual execution state, attempts, retry timing, errors, and exact result IDs.
  `workflow_links` binds task/reminder records; `workflow_notifications` stores step-owned alerts.
- The existing one-second runtime worker advances ready steps and reconciles linked completion.
  Task page/API updates and reminder actions reconcile immediately; legacy scheduling-handler
  updates are also reconciled by the worker.
- Each local side effect and its step result commit in **one SQLite transaction**. Completed
  steps are skipped on retries and restart. Failure/crash before that commit rolls back the
  artifact as well as the claimed step, so it can be retried without an orphan or duplicate.
- Ready steps are conditionally claimed, and submissions and notification steps have unique
  database constraints. The runtime also serializes local mutations with the shared lock.
- Step states are `pending`, `waiting`, `completed`, `failed`, or `cancelled`; a transient
  `running` claim exists within the step transaction. Workflow states are `running`, `completed`,
  `failed`, or `cancelled`.
- A workflow is completed when all its steps are completed. Creation steps track artifact
  creation, not a task's eventual completion. An explicit `wait_for_reminder` with `until:
  "completed"` tracks linked completion; chat adds this for linked task/reminder combinations.
- A failing step gets at most **three attempts per retry cycle**, with delays of 1 then
  2 seconds. Exhaustion marks the workflow failed. Its dependencies remain blocked.
  **Retry failed steps** resets only failed steps for another cycle; completed results and
  total attempt counts remain intact. Terminal cancelled/completed workflows cannot be retried.
- Disabling the workflow capability gates new plans. Disabling timers/notifications prevents
  corresponding new step effects and follows the retry policy; already-created reminders
  continue running. Enable choices and retry deadlines survive restart.
- **Cancel workflow** cancels pending/retrying/waiting steps, cancels its active reminders,
  and suppresses its pending notifications. Already-created tasks/calendar events remain.
  Cancellation is idempotent; an execution-completed workflow cannot be cancelled.
- Cancelling a reminder that a workflow is waiting on cancels that workflow's remaining work.
  Deleting a linked task clears the link; completing its reminder does not recreate the task.

Workflow status appears beside reminder widgets in chat. The panel shows each step, failures,
retry availability, and cancellation controls. Its move/close/restore behavior is persistent;
closing a widget leaves execution running. Controls retain keyboard focus across polling.

## Notifications and runtime availability

Workflow notifications share `/api/workspace/notifications` and its explicit acknowledgement
endpoint with reminder alerts. Reads are non-consuming and delivery is at least once. A
visible chat page displays pending alerts; other pages, hidden tabs, or a closed browser defer
display. Workflows continue while the backend is running. When it is stopped, execution
resumes on restart, including overdue reminders, waiting dependencies, and scheduled retries.

## Verification and extension seams

Run the isolated backend suite and frontend/browser suite from the repository root:

```sh
venv/bin/python backend/tests/run_isolated.py -q backend/tests/ --tb=short --disable-warnings
node --test frontend/tests/*.test.cjs
```

`backend/tests/test_workflows_phase2.py` covers graph validation, full-plan clarification,
idempotent submission, atomic rollback/crash recovery, bounded/manual retry, linked completion,
calendar execution, cancellation, restart recovery, and foreign-key-safe workspace reset.

The Firefox test uses a disposable real backend and browser. It verifies failed-step state
across restart, UI retry without recreating the task, reload/mobile status panels, linked
completion, UI cancellation, and a reminder-dependent task running exactly once across
two further backend restarts. Phase 1 timer and notification checks remain in the same test.

`backend/workflow_planner.py` owns schemas and bounded chat composition;
`backend/workflow_runtime.py` owns durable execution; `frontend/js/workspace-runtime.js`
renders the allowlisted workflow panel. Future capabilities can extend those controlled
interfaces. Phase 3's declarative component composition and later extension/feedback tooling
remain separate implementation work.
