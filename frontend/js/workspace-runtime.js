// Only registered, developer-owned renderers consume JSON props. Never run code from plans.
class WorkspaceRuntime {
    constructor(host = document.getElementById('workspaceComponents')) {
        this.host = host;
        this.cards = new Map();
        this.delivered = new Set();
        this.pendingAcks = new Set();
        this.busy = false;
        this.mutating = false;
        this.refreshAgain = false;
        this.version = 0;
        this.renderers = { reminder: component => this.reminderCard(component),
            workflow: component => this.workflowCard(component),
            panel: component => this.declarativeCard(component) };
    }

    start() {
        if (!this.host || this.pollTimer) return;
        void this.refresh();
        this.pollTimer = setInterval(() => void this.refresh(), 1000);
        this.countdownTimer = setInterval(() => this.updateCountdowns(), 250);
        this.visibilityListener = () => { if (!document.hidden) void this.refresh(); };
        document.addEventListener('visibilitychange', this.visibilityListener);
    }

    stop() {
        clearInterval(this.pollTimer);
        clearInterval(this.countdownTimer);
        this.pollTimer = null;
        document.removeEventListener('visibilitychange', this.visibilityListener);
    }

    async refresh() {
        if (!this.host) return;
        if (this.busy || this.mutating) { this.refreshAgain = true; return; }
        this.busy = true;
        const version = this.version;
        try {
            const components = await API.getWorkspaceComponents();
            // A response begun before a user action must not replace the action's state.
            if (!this.mutating && version === this.version) this.render(components);
            else this.refreshAgain = true;
            if (!document.hidden) await this.deliverNotifications();
            this.host.dataset.offline = 'false';
            this.host.title = '';
        } catch (error) {
            this.host.dataset.offline = 'true';
            this.host.title = 'Workspace is offline. Timers and workflows will reconnect automatically.';
            // Keep the last known widgets instead of clearing them or flooding toasts.
        } finally {
            this.busy = false;
            if (this.refreshAgain && !this.mutating) {
                this.refreshAgain = false;
                void this.refresh();
            }
        }
    }

    async deliverNotifications() {
        const notifications = await API.getWorkspaceNotifications();
        for (const notification of notifications) {
            if (document.hidden) return;
            if (!this.delivered.has(notification.id)) {
                // Do not consume an alert until a visible document has a mounted toast.
                const element = toast(notification.message, 'info', 10000);
                if (!element?.isConnected) continue;
                await new Promise(resolve => requestAnimationFrame(resolve));
                if (document.hidden || !element.isConnected) continue;
                this.delivered.add(notification.id);
                this.pendingAcks.add(notification.id);
            }
        }
        // Ack failures retry independently, without producing duplicate toasts in this page.
        for (const id of this.pendingAcks) {
            try {
                await API.ackWorkspaceNotification(id);
                this.pendingAcks.delete(id);
            } catch (_) { /* retry on the next poll */ }
        }
    }

    node(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    button(text, label, action, disabled = false) {
        const button = this.node('button', 'workspace-button', text);
        button.type = 'button';
        button.setAttribute('aria-label', label);
        button.dataset.control = action;
        button.disabled = disabled;
        return button;
    }

    reminderCard(component) {
        const noun = component.kind === 'workflow' ? 'workflow' : 'reminder';
        const card = this.node('article', 'workspace-card');
        card.dataset.componentId = component.id;
        const heading = this.node('div', 'workspace-card-heading');
        const title = this.node('h3', 'workspace-card-title');
        title.id = `workspace-title-${component.id}`;
        card.setAttribute('aria-labelledby', title.id);
        const controls = this.node('div', 'workspace-card-controls');
        controls.append(this.button('↑', `Move ${noun} earlier`, 'earlier'),
            this.button('↓', `Move ${noun} later`, 'later'),
            this.button('×', `Close widget; ${noun} keeps running`, 'close'));
        heading.append(title, controls);
        const countdown = this.node('div', 'workspace-countdown');
        countdown.setAttribute('role', 'timer');
        countdown.setAttribute('aria-live', 'off');
        const status = this.node('p', 'workspace-status');
        status.setAttribute('role', 'status');
        const actions = this.node('div', 'workspace-card-actions');
        card.append(heading, countdown, status, actions);
        card.addEventListener('click', event => {
            const button = event.target.closest('button[data-control]');
            if (button && !button.disabled) void this.act(component.id, button.dataset.control);
        });
        return { card, title, countdown, status, actions, controls, component };
    }

    workflowCard(component) {
        if (component.template) return this.declarativeCard(component);
        const entry = this.reminderCard(component);
        entry.card.classList.add('workspace-workflow');
        entry.countdown.hidden = true;
        entry.steps = this.node('ol', 'workspace-workflow-steps');
        entry.card.insertBefore(entry.steps, entry.actions);
        return entry;
    }

    declarativeCard(component) {
        const card = this.node('article', 'workspace-card workspace-template-card');
        card.dataset.componentId = component.id;
        const heading = this.node('div', 'workspace-card-heading');
        const title = this.node('h3', 'workspace-card-title');
        title.id = `workspace-title-${component.id}`;
        card.setAttribute('aria-labelledby', title.id);
        const controls = this.node('div', 'workspace-card-controls');
        controls.append(this.button('↑', 'Move component earlier', 'earlier'),
            this.button('↓', 'Move component later', 'later'),
            this.button('×', 'Close component; execution continues', 'close'),
            this.button('Archive', 'Archive component', 'archive'));
        heading.append(title, controls);
        const body = this.node('div', 'workspace-template-body');
        const status = this.node('p', 'workspace-status');
        status.setAttribute('role', 'status');
        const actions = this.node('div', 'workspace-card-actions');
        card.append(heading, body, status, actions);
        card.addEventListener('click', event => {
            const button = event.target.closest('button[data-control]');
            if (button && !button.disabled) void this.act(component.id, button.dataset.control);
        });
        return { card, title, body, status, actions, controls, component, declarative: true };
    }

    renderDeclarative(entry, component) {
        const definition = component.template.definition;
        const props = component.props || {};
        const completed = Number(props.completed_steps ?? 0);
        const total = Number(props.total_steps ?? (Array.isArray(props.steps) ? props.steps.length : 0));
        const values = { ...props, completed_steps: completed, total_steps: total,
            progress: Number.isFinite(Number(props.progress)) ? Number(props.progress) : (total ? completed / total : 0) };
        const key = JSON.stringify({ template: component.template.version, props: values });
        if (key !== entry.templateKey) {
            entry.templateKey = key;
            entry.body.replaceChildren();
            for (const nodeDefinition of definition.nodes) {
                const value = values[nodeDefinition.source];
                if (nodeDefinition.type === 'text') {
                    const text = this.node('p', 'workspace-template-text', String(value ?? ''));
                    if (nodeDefinition.label) text.setAttribute('aria-label', nodeDefinition.label);
                    entry.body.append(text);
                } else if (nodeDefinition.type === 'status') {
                    entry.body.append(this.node('p', 'workspace-template-status', `${nodeDefinition.label ? `${nodeDefinition.label}: ` : ''}${String(value ?? '')}`));
                } else if (nodeDefinition.type === 'progress') {
                    const wrapper = this.node('div', 'workspace-template-progress');
                    const progress = document.createElement('progress');
                    progress.max = 1; progress.value = Math.max(0, Math.min(1, Number(value) || 0));
                    progress.setAttribute('aria-label', nodeDefinition.label || 'Workflow progress');
                    wrapper.append(progress, this.node('span', 'workspace-progress-text', `${Math.round(progress.value * 100)}%`));
                    entry.body.append(wrapper);
                } else if (nodeDefinition.type === 'list') {
                    const list = this.node('ol', 'workspace-template-list');
                    for (const item of Array.isArray(value) ? value : []) {
                        const row = this.node('li', 'workspace-template-list-item', `${item.action || 'Step'} · ${item.status || ''}`);
                        if (item.error) row.append(this.node('span', 'workspace-step-error', item.error));
                        list.append(row);
                    }
                    entry.body.append(list);
                }
            }
        }
        entry.title.textContent = props.title || props.label || component.template.name;
        entry.status.textContent = total
            ? `${props.status || 'active'} · ${completed}/${total} steps complete`
            : `${props.status || 'active'} · template v${component.template.version}`;
        const actionsKey = `${props.status}:${props.can_retry}:${component.template.can_upgrade}`;
        if (actionsKey !== entry.templateActionsKey) {
            entry.templateActionsKey = actionsKey;
            entry.actions.replaceChildren();
            for (const action of definition.actions || []) {
                const allowed = action.action === 'retry' ? props.can_retry
                    : action.action === 'cancel' ? ['running', 'failed'].includes(props.status) : true;
                if (allowed) entry.actions.append(this.button(action.label, action.label, action.action));
            }
            if (component.template.can_upgrade) entry.actions.append(this.button(
                `Upgrade to v${component.template.current_version}`, 'Upgrade component template', 'upgrade'));
        }
    }

    updateWorkflow(entry, props) {
        const completed = props.steps.filter(step => step.status === 'completed').length;
        const status = `${props.status} · ${completed}/${props.steps.length} steps complete`;
        if (entry.status.textContent !== status) entry.status.textContent = status;
        const key = JSON.stringify(props.steps);
        if (key !== entry.stepsKey) {
            entry.stepsKey = key;
            entry.steps.replaceChildren();
            const labels = { create_task: 'Create task', create_calendar_event: 'Create calendar event',
                create_reminder: 'Create reminder', wait_for_reminder: 'Wait for reminder', notify: 'Notify' };
            for (const step of props.steps) {
                const item = this.node('li', 'workspace-workflow-step');
                item.dataset.status = step.status;
                const heading = this.node('div', 'workspace-step-heading');
                heading.append(this.node('span', '', labels[step.action] || step.action),
                    this.node('span', 'workspace-step-state', step.status));
                item.append(heading);
                if (step.action === 'wait_for_reminder' && step.status === 'waiting') {
                    const definition = props.plan.steps.find(definition => definition.id === step.id);
                    item.append(this.node('p', 'workspace-step-detail', definition?.inputs.until === 'completed'
                        ? 'Waiting for the linked task or reminder to be completed.' : 'Waiting for the reminder deadline.'));
                }
                if (step.error) item.append(this.node('p', 'workspace-step-error', step.error));
                if (step.status === 'failed') item.append(this.node('p', 'workspace-step-detail',
                    step.next_attempt_at ? `Attempt ${step.attempts} failed · automatic retry scheduled` : `Failed after ${step.attempts} attempts`));
                entry.steps.append(item);
            }
        }
        const actionsKey = `${props.status}:${props.can_retry}`;
        if (actionsKey !== entry.actionsKey) {
            entry.actionsKey = actionsKey;
            entry.actions.replaceChildren();
            if (props.can_retry) entry.actions.append(this.button('Retry failed steps', `Retry failed steps in ${props.title}`, 'retry'));
            if (['running', 'failed'].includes(props.status)) entry.actions.append(this.button('Cancel workflow', `Cancel ${props.title}`, 'cancel'));
        }
    }

    render(components) {
        const focus = document.activeElement;
        const focusCard = focus?.closest?.('[data-component-id]')?.dataset.componentId;
        const focusControl = focus?.dataset.control;
        const visible = components.filter(component => component.visible && component.lifecycle !== 'archived' && this.renderers[component.kind]);
        const ids = new Set(visible.map(component => component.id));
        for (const [id, entry] of this.cards) {
            if (!ids.has(id)) { entry.card.remove(); this.cards.delete(id); }
        }
        visible.forEach((component, index) => {
            let entry = this.cards.get(component.id);
            if (!entry) {
                entry = this.renderers[component.kind](component);
                this.cards.set(component.id, entry);
            }
            const props = component.props;
            const oldState = entry.component.props.status;
            entry.component = component;
            if (entry.title.textContent !== props.label) entry.title.textContent = props.label;
            entry.controls.children[0].disabled = index === 0;
            entry.controls.children[1].disabled = index === visible.length - 1;
            if (entry.declarative) {
                this.renderDeclarative(entry, component);
            } else if (component.kind === 'workflow') {
                this.updateWorkflow(entry, props);
            } else {
                const status = (props.status === 'due' ? 'Reminder due' : props.status) + (props.task_id ? ' · linked task' : '');
                if (entry.status.textContent !== status) entry.status.textContent = status;
            }
            if (component.kind === 'reminder' && (!entry.actions.children.length || oldState !== props.status)) {
                entry.actions.replaceChildren();
                if (props.status === 'active' || props.status === 'paused') {
                    const paused = props.status === 'paused';
                    entry.actions.append(this.button(paused ? 'Resume' : 'Pause',
                        `${paused ? 'Resume' : 'Pause'} ${props.label}`, paused ? 'resume' : 'pause'));
                }
                if (['active', 'paused', 'due'].includes(props.status)) {
                    entry.actions.append(this.button('Done', `Complete ${props.label}`, 'complete'),
                        this.button('Cancel', `Cancel ${props.label}`, 'cancel'));
                }
            }
            const current = this.host.children[index];
            if (current !== entry.card) this.host.insertBefore(entry.card, current || null);
        });
        this.renderClosed(components.filter(component => (!component.visible || component.lifecycle === 'archived') && this.renderers[component.kind]));
        this.host.hidden = !visible.length && !components.some(component => !component.visible);
        this.updateCountdowns();
        // Moving a focused node or replacing action buttons must retain keyboard position.
        if (focusCard && focusControl && !document.activeElement?.closest?.('[data-component-id]')) {
            const card = this.cards.get(focusCard)?.card;
            const control = card?.querySelector(`[data-control="${focusControl}"]`);
            if (control && !control.disabled) control.focus();
            else card?.querySelector('button:not(:disabled)')?.focus();
        }
        if (this.focusRequest) {
            const { componentId, control } = this.focusRequest;
            const card = this.cards.get(componentId)?.card;
            const button = card?.querySelector(`[data-control="${control}"]`);
            if (button && !button.disabled) button.focus();
            else (card || this.host).querySelector('button:not(:disabled), summary')?.focus();
            this.focusRequest = null;
        }
    }

    renderClosed(components) {
        if (!this.closed) {
            this.closed = this.node('details', 'workspace-closed');
            this.closedSummary = this.node('summary', '', '');
            this.closedList = this.node('div', 'workspace-closed-list');
            this.closed.append(this.closedSummary, this.closedList);
        }
        this.closed.hidden = !components.length;
        this.closedSummary.textContent = `Closed widgets (${components.length})`;
        // Leave controls mounted on unchanged polls to preserve focus.
        const key = JSON.stringify(components.map(component => [component.id, component.props.label || component.props.title, component.lifecycle]));
        if (key !== this.closedKey) {
            this.closedKey = key;
            this.closedList.replaceChildren();
            for (const component of components) {
                const label = component.props.label || component.props.title || 'component';
                const action = component.lifecycle === 'archived' ? 'restore' : 'show';
                const button = this.button(`${action === 'restore' ? 'Restore' : 'Show'} ${label}`,
                    `${action === 'restore' ? 'Restore' : 'Show'} ${label}`, action);
                button.addEventListener('click', () => void this.act(component.id, action));
                this.closedList.append(button);
            }
        }
        if (this.host.lastElementChild !== this.closed) this.host.append(this.closed);
    }

    updateCountdowns() {
        for (const entry of this.cards.values()) {
            if (entry.component.kind === 'workflow') continue;
            const props = entry.component.props;
            let seconds = props.status === 'active'
                ? Math.max(0, Math.ceil((Date.parse(props.due_at) - Date.now()) / 1000))
                : Math.ceil(props.remaining_seconds);
            if (!Number.isFinite(seconds)) seconds = 0;
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor(seconds % 3600 / 60);
            const time = `${hours ? hours + ':' : ''}${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
            if (entry.countdown.textContent !== time) entry.countdown.textContent = time;
            if (props.status === 'active' && seconds === 0) entry.status.textContent = 'Waiting for reminder notification…';
        }
    }

    async act(componentId, action) {
        if (this.mutating) return;
        this.mutating = true;
        this.version++;
        const entry = this.cards.get(componentId);
        if (entry?.card.contains(document.activeElement) || action === 'show') {
            const control = action === 'pause' ? 'resume' : action === 'resume' ? 'pause'
                : ['complete', 'cancel', 'show'].includes(action) ? 'close' : action;
            this.focusRequest = { componentId, control };
        }
        entry?.card.querySelectorAll('button').forEach(button => { button.disabled = true; });
        try {
            if (['archive', 'restore', 'upgrade'].includes(action)) {
                await API.actOnWorkspaceComponent(componentId, action);
            } else if (['earlier', 'later', 'close', 'show'].includes(action)) {
                await API.updateWorkspaceComponent(componentId, action === 'close' || action === 'show'
                    ? { visible: action === 'show' } : { move: action });
            } else if (entry?.component.kind === 'workflow') {
                await API.actOnWorkflow(entry.component.props.id, action);
            } else if (entry) {
                await API.actOnReminder(entry.component.props.id, action);
            }
        } catch (error) {
            toast(error.message || 'Could not update workspace widget.', 'error');
        } finally {
            entry?.card.querySelectorAll('button').forEach(button => { button.disabled = false; });
            this.mutating = false;
            await this.refresh();
        }
    }
}

window.WorkspaceRuntime = WorkspaceRuntime;
window.workspaceRuntime = new WorkspaceRuntime();
document.addEventListener('DOMContentLoaded', () => window.workspaceRuntime.start());
