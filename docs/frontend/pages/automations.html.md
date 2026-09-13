# `frontend/pages/automations.html`

Automation rule builder and completed-run history page.

## User workflows

- Create an email rule with a name, condition, optional details, and selected actions.
- Enable, pause, or delete an existing rule.
- Review completed runs in the Done section.
- Download saved email attachments and open generated tasks from run artifacts.
- See a clear note that rules run automatically during email sync and have no manual trigger.

## API calls

- `GET /api/automations` loads rules.
- `POST /api/automations` creates a rule.
- `PUT /api/automations/{rule_id}` toggles enabled state.
- `DELETE /api/automations/{rule_id}` removes a rule.
- `GET /api/automations/done` loads run history.
- `GET /api/automations/attachments/{attachment_id}/download` downloads a saved attachment.

The page escapes user-controlled names, conditions, details, and artifact labels before inserting them into the DOM.
