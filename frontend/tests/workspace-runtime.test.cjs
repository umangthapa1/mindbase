const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../js/workspace-runtime.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
    let resolve;
    const promise = new Promise(yes => { resolve = yes; });
    return { promise, resolve };
}

function fixture(overrides = {}) {
    const state = { toasts: [], acks: [], renders: [] };
    const document = { hidden: false, getElementById: () => null,
        addEventListener() {}, removeEventListener() {} };
    const context = vm.createContext({ document, console, setInterval, clearInterval,
        requestAnimationFrame: callback => callback(),
        API: { getWorkspaceComponents: async () => [], getWorkspaceNotifications: async () => [],
            ackWorkspaceNotification: async id => state.acks.push(id), ...overrides },
        toast: message => { state.toasts.push(message); return { isConnected: true }; },
    });
    context.window = context;
    vm.runInContext(source, context);
    const host = { dataset: {}, title: '', querySelector: () => null };
    const runtime = new context.WorkspaceRuntime(host);
    runtime.render = components => state.renders.push(components);
    return { context, document, runtime, state };
}

test('notification reads acknowledge only after a connected toast is rendered', async () => {
    const fixtureData = fixture({ getWorkspaceNotifications: async () => [{ id: 'n', message: '<img onerror=evil()>' }] });
    const { context, runtime, state } = fixtureData;
    context.requestAnimationFrame = callback => { assert.deepEqual(state.acks, []); callback(); };
    await runtime.refresh();
    assert.deepEqual(state.toasts, ['<img onerror=evil()>']);
    assert.deepEqual(state.acks, ['n']);
});

test('hidden documents do not consume notifications', async () => {
    let reads = 0;
    const { document, runtime, state } = fixture({ getWorkspaceNotifications: async () => { reads++; return [{ id: 'n' }]; } });
    document.hidden = true;
    await runtime.refresh();
    assert.equal(reads, 0);
    assert.deepEqual(state.acks, []);
});

test('failed rendering or hiding before the paint leaves notifications pending', async () => {
    for (const failure of ['unmounted', 'hidden']) {
        const { context, document, runtime, state } = fixture({ getWorkspaceNotifications: async () => [{ id: 'n' }] });
        if (failure === 'unmounted') context.toast = () => ({ isConnected: false });
        else context.requestAnimationFrame = callback => { document.hidden = true; callback(); };
        await runtime.refresh();
        assert.deepEqual(state.acks, []);
        assert.equal(runtime.delivered.size, 0);
    }
});

test('an ack failure retries without showing the same toast again', async () => {
    let attempts = 0;
    const { runtime, state } = fixture({
        getWorkspaceNotifications: async () => [{ id: 'n', message: 'Grandpa' }],
        ackWorkspaceNotification: async () => { if (++attempts === 1) throw new Error('offline'); },
    });
    await runtime.refresh();
    assert.equal(runtime.pendingAcks.size, 1);
    await runtime.refresh();
    assert.equal(attempts, 2);
    assert.equal(runtime.pendingAcks.size, 0);
    assert.deepEqual(state.toasts, ['Grandpa']);
});

test('offline refresh retains existing widgets and avoids repeated error toasts', async () => {
    const { runtime, state } = fixture({ getWorkspaceComponents: async () => { throw new Error('offline'); } });
    await runtime.refresh();
    await runtime.refresh();
    assert.equal(runtime.host.dataset.offline, 'true');
    assert.deepEqual(state.renders, []);
    assert.deepEqual(state.toasts, []);
});

test('a poll response that predates an action cannot render stale state', async () => {
    const pending = deferred();
    let reads = 0;
    const { runtime, state } = fixture({
        getWorkspaceComponents: () => ++reads === 1 ? pending.promise : Promise.resolve(['fresh']),
        updateWorkspaceComponent: async () => {},
    });
    const refreshing = runtime.refresh();
    await runtime.act('component', 'close');
    pending.resolve(['stale']);
    await refreshing;
    await tick();
    assert.deepEqual(state.renders, [['fresh']]);
});

test('countdowns derive from UTC deadlines and paused values stay fixed', () => {
    const { context, runtime } = fixture();
    const deadline = new Date(Date.now() + 30000).toISOString();
    const active = { component: { props: { status: 'active', due_at: deadline, remaining_seconds: 6000 } },
        countdown: { textContent: '' }, status: {} };
    const paused = { component: { props: { status: 'paused', due_at: null, remaining_seconds: 18.75 } },
        countdown: { textContent: '' }, status: {} };
    runtime.cards.set('a', active);
    runtime.cards.set('p', paused);
    runtime.updateCountdowns();
    assert.equal(active.countdown.textContent, '00:30');
    assert.equal(paused.countdown.textContent, '00:19');
    active.component.props.due_at = new Date(Date.now() - 1000).toISOString();
    runtime.updateCountdowns();
    assert.equal(active.countdown.textContent, '00:00');
    assert.match(active.status.textContent, /Waiting/);
});

// Leaf DOM nodes for the workflow status renderer; browser coverage uses real DOM.
function leaf(tag, className, text = '') {
    return { tag, className, textContent: text, children: [], attributes: {}, dataset: {},
        setAttribute(key, value) { this.attributes[key] = value; },
        addEventListener() {},
        append(...nodes) { this.children.push(...nodes); },
        replaceChildren(...nodes) { this.children = nodes; },
        set innerHTML(_) { throw new Error('Workflow content must use text nodes'); },
    };
}

test('workflow status shows failed steps as text with retry and cancel controls', () => {
    const { runtime } = fixture();
    runtime.node = leaf;
    const entry = { status: leaf('p'), steps: leaf('ol'), actions: leaf('div') };
    const props = { title: 'Create and confirm', status: 'failed', can_retry: true,
        steps: [{ id: 'task', action: 'create_task', status: 'completed', attempts: 1 },
            { id: 'notice', action: 'notify', status: 'failed', attempts: 3, error: '<img onerror=evil()>', next_attempt_at: null }],
        plan: { steps: [] },
    };
    runtime.updateWorkflow(entry, props);
    assert.equal(entry.status.textContent, 'failed · 1/2 steps complete');
    assert.deepEqual(entry.actions.children.map(button => button.dataset.control), ['retry', 'cancel']);
    assert.equal(entry.steps.children[1].children[1].textContent, '<img onerror=evil()>');
    props.status = 'completed';
    props.can_retry = false;
    props.steps[1] = { ...props.steps[1], status: 'completed', error: null };
    runtime.updateWorkflow(entry, props);
    assert.equal(entry.status.textContent, 'completed · 2/2 steps complete');
    assert.equal(entry.actions.children.length, 0);
});

test('waiting workflow explains completion condition and preserves nodes on unchanged polls', () => {
    const { runtime } = fixture();
    runtime.node = leaf;
    const entry = { status: leaf('p'), steps: leaf('ol'), actions: leaf('div') };
    const props = { title: 'Call grandpa', status: 'running', can_retry: false,
        steps: [{ id: 'done', action: 'wait_for_reminder', status: 'waiting' }],
        plan: { steps: [{ id: 'done', inputs: { until: 'completed' } }] },
    };
    runtime.updateWorkflow(entry, props);
    const node = entry.steps.children[0], button = entry.actions.children[0];
    assert.match(node.children[1].textContent, /linked task or reminder/);
    runtime.updateWorkflow(entry, props);
    assert.equal(entry.steps.children[0], node);
    assert.equal(entry.actions.children[0], button);
});

test('workflow controls call the workflow API rather than a reminder action', async () => {
    const calls = [];
    const { runtime } = fixture({
        actOnWorkflow: async (...args) => calls.push(args),
        actOnReminder: async () => { throw new Error('Wrong API'); },
    });
    runtime.cards.set('component', { component: { kind: 'workflow', props: { id: 'workflow-id' } },
        card: { contains: () => false, querySelectorAll: () => [] } });
    await runtime.act('component', 'retry');
    assert.deepEqual(calls, [['workflow-id', 'retry']]);
});

test('workflow API sends a stable supplied idempotency key and encodes action IDs', async () => {
    const calls = [];
    const context = vm.createContext({ crypto: { randomUUID: () => 'new-intent' },
        fetch: async (...args) => { calls.push(args); return { ok: true, json: async () => ({}) }; },
    });
    vm.runInContext(readFileSync(join(__dirname, '../js/api.js'), 'utf8'), context);
    await vm.runInContext('API.createWorkflow({title: "Test", steps: []}, "stable-request")', context);
    await vm.runInContext('API.createWorkflow({title: "Test", steps: []}, "stable-request")', context);
    assert.equal(calls[0][0], '/api/workspace/workflows');
    assert.equal(JSON.parse(calls[0][1].body).idempotency_key, 'stable-request');
    assert.equal(calls[0][1].body, calls[1][1].body);
    await vm.runInContext('API.actOnWorkflow("id/with space", "cancel")', context);
    assert.equal(calls[2][0], '/api/workspace/workflows/id%2Fwith%20space/actions');
});

test('declarative templates render only text, progress, lists, and allowlisted actions', () => {
    const { context, runtime } = fixture();
    runtime.node = leaf;
    context.document.createElement = tag => leaf(tag);
    const component = { id: 'panel', kind: 'panel', props: {
        title: '<img onerror=evil()>', status: 'running', progress: 0.5,
        steps: [{ action: 'notify', status: 'failed', error: '<script>bad()</script>' }], can_retry: true,
    }, template: { name: 'Safe panel', version: 1, current_version: 2, can_upgrade: true,
        definition: { layout: 'stack', nodes: [
            { id: 'title', type: 'text', source: 'title' }, { id: 'status', type: 'status', source: 'status' },
            { id: 'progress', type: 'progress', source: 'progress' }, { id: 'steps', type: 'list', source: 'steps' },
        ], actions: [{ id: 'retry', label: 'Retry', action: 'retry' }] } } };
    const entry = runtime.declarativeCard(component);
    runtime.renderDeclarative(entry, component);
    assert.equal(entry.title.textContent, '<img onerror=evil()>');
    assert.equal(entry.body.children.length, 4);
    assert.equal(entry.body.children[2].children[0].value, 0.5);
    assert.equal(entry.body.children[3].children[0].textContent, 'notify · failed');
    assert.equal(entry.body.children[3].children[0].children[0].textContent, '<script>bad()</script>');
    assert.deepEqual(entry.actions.children.map(button => button.dataset.control), ['retry', 'upgrade']);
});

test('archived template components are restored through component lifecycle API', async () => {
    const calls = [];
    const { runtime } = fixture({ actOnWorkspaceComponent: async (...args) => calls.push(args) });
    runtime.cards.set('panel', { component: { kind: 'panel', props: { id: 'ignored' } },
        card: { contains: () => false, querySelectorAll: () => [] } });
    await runtime.act('panel', 'archive');
    assert.deepEqual(calls, [['panel', 'archive']]);
});
