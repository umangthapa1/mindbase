const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const { once } = require('node:events');
const { mkdtempSync, writeFileSync, rmSync, existsSync } = require('node:fs');
const { createServer } = require('node:net');
const { join, resolve } = require('node:path');
const { test } = require('node:test');

const root = resolve(__dirname, '../..');
const firefox = process.env.FIREFOX_BIN || 'firefox';
const python = process.env.MINDBASE_TEST_PYTHON || join(root, 'venv/bin/python');
const available = existsSync(python) && spawnSync(firefox, ['--version'], { timeout: 10000 }).status === 0;
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function waitFor(read, check, description, timeout = 15000) {
    const deadline = Date.now() + timeout;
    let result;
    do {
        try { result = await read(); if (check(result)) return result; } catch (_) { /* server may be restarting */ }
        await sleep(100);
    } while (Date.now() < deadline);
    throw new Error(`Timed out: ${description}; last result: ${JSON.stringify(result)}`);
}

test('real runtime: reminders and durable workflow retry, cancellation, linked completion and restart', {
    skip: !available && 'Requires Firefox and the project Python environment', timeout: 150000,
}, async t => {
    const fixture = mkdtempSync('/tmp/omnirush/mindbase-runtime-browser-');
    const workspace = join(fixture, 'workspace');
    const profile = join(fixture, 'profile');
    // The Firefox profile directory must exist before writing its isolated preferences.
    const { mkdirSync } = require('node:fs');
    mkdirSync(profile);
    const portServer = createServer();
    portServer.listen(0, '127.0.0.1');
    await once(portServer, 'listening');
    const port = portServer.address().port;
    await new Promise(resolve => portServer.close(resolve));
    const base = `http://127.0.0.1:${port}`;
    let server, browser, ws;
    t.after(async () => {
        ws?.close();
        for (const process of [browser, server]) {
            if (process && process.exitCode === null && process.signalCode === null) {
                process.kill('SIGKILL');
                await once(process, 'exit');
            }
        }
        rmSync(fixture, { recursive: true, force: true });
    });

    const api = async (path, options) => {
        const response = await fetch(base + '/api' + path, options);
        assert.ok(response.ok, `${path}: ${response.status} ${await response.clone().text()}`);
        return response.json();
    };
    const startServer = async () => {
        server = spawn(python, [join(root, 'backend/tests/serve_runtime_fixture.py'),
            '--workspace', workspace, '--port', String(port)], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
        let output = '';
        server.stderr.on('data', data => { output += data; });
        server.stdout.on('data', data => { output += data; });
        try {
            await waitFor(() => api('/workspace/components'), Array.isArray, 'isolated backend startup', 30000);
        } catch (error) { throw new Error(`${error.message}\n${output}`); }
    };
    const stopServer = async () => {
        const stopped = once(server, 'exit');
        server.kill('SIGTERM');
        await stopped;
    };
    await startServer();
    const prefs = {
        'browser.shell.checkDefaultBrowser': false, 'browser.startup.page': 0,
        'browser.startup.homepage': 'about:blank', 'browser.newtabpage.enabled': false,
        'ui.prefersReducedMotion': 1, 'browser.safebrowsing.phishing.enabled': false,
        'browser.safebrowsing.malware.enabled': false, 'datareporting.policy.dataSubmissionEnabled': false,
        'toolkit.telemetry.enabled': false, 'network.prefetch-next': false, 'network.dns.disablePrefetch': true,
        'network.proxy.type': 1, 'network.proxy.http': '127.0.0.1', 'network.proxy.http_port': 9,
        'network.proxy.ssl': '127.0.0.1', 'network.proxy.ssl_port': 9,
        'network.proxy.no_proxies_on': 'localhost, 127.0.0.1',
    };
    writeFileSync(join(profile, 'user.js'), Object.entries(prefs)
        .map(([key, value]) => `user_pref(${JSON.stringify(key)}, ${JSON.stringify(value)});`).join('\n'));
    browser = spawn(firefox, ['--headless', '--no-remote', '--profile', profile,
        '--remote-debugging-port', '0', 'about:blank'], { stdio: ['ignore', 'pipe', 'pipe'] });
    const endpoint = await new Promise((resolve, reject) => {
        let output = '';
        const timer = setTimeout(() => reject(new Error(`Firefox startup timed out: ${output}`)), 15000);
        const listen = chunk => {
            output += chunk;
            const match = output.match(/WebDriver BiDi listening on (ws:\/\/\S+)/);
            if (match) { clearTimeout(timer); resolve(`${match[1]}/session`); }
        };
        browser.stderr.on('data', listen);
        browser.stdout.on('data', listen);
        browser.once('error', error => { clearTimeout(timer); reject(error); });
    });
    ws = new WebSocket(endpoint);
    await once(ws, 'open');
    const requests = new Map();
    let nextId = 0;
    ws.addEventListener('message', ({ data }) => {
        const message = JSON.parse(data);
        const pending = requests.get(message.id);
        if (!pending) return;
        requests.delete(message.id);
        clearTimeout(pending.timer);
        if (message.type === 'error') pending.reject(new Error(JSON.stringify(message)));
        else pending.resolve(message.result);
    });
    const call = (method, params) => new Promise((resolve, reject) => {
        const id = ++nextId;
        const timer = setTimeout(() => { requests.delete(id); reject(new Error(`${method} timed out`)); }, 15000);
        requests.set(id, { resolve, reject, timer });
        ws.send(JSON.stringify({ id, method, params }));
    });
    await call('session.new', { capabilities: {} });
    const { context } = await call('browsingContext.create', { type: 'tab' });
    const evaluate = async body => {
        const result = await call('script.evaluate', { expression: `(async () => { return JSON.stringify(await (async () => { ${body} })()); })()`,
            target: { context }, awaitPromise: true });
        assert.equal(result.type, 'success', JSON.stringify(result));
        return JSON.parse(result.result.value);
    };
    const waitForCards = count => waitFor(() => evaluate('return document.querySelectorAll(".workspace-card").length;'),
        value => value === count, `${count} visible widgets`);
    const selector = (id, action) => `.workspace-card[data-component-id="${id}"] [data-control="${action}"]`;
    const click = async (id, action) => evaluate(`const button = document.querySelector(${JSON.stringify(selector(id, action))});
        if (!button || button.disabled) throw new Error('Missing or disabled ${action} control'); button.focus(); button.click(); return true;`);
    const send = async text => {
        await evaluate(`document.querySelector('#messageInput').value = ${JSON.stringify(text)};
            await chatManager.sendMessage(); return true;`);
    };
    const reload = async () => {
        await call('browsingContext.reload', { context, wait: 'complete' });
        await waitFor(() => evaluate('return Boolean(chatManager.currentConversationId) && !chatManager.isConversationLoading;'),
            Boolean, 'chat ready after reload');
    };
    await call('browsingContext.navigate', { context, url: base, wait: 'complete' });
    await waitFor(() => evaluate('return Boolean(chatManager.currentConversationId) && !chatManager.isConversationLoading;'), Boolean, 'chat initialization');
    await send('remind me to check on grandpa in 30 seconds');
    await waitForCards(1);
    const grandpa = (await api('/workspace/reminders'))[0];
    assert.equal(grandpa.label, 'Check on grandpa');
    assert.equal((await api('/tasks')).count, 0);
    const countdown = () => evaluate(`return document.querySelector('[data-component-id="${grandpa.component_id}"] .workspace-countdown').textContent;`);
    const initialCountdown = await countdown();
    await sleep(1300);
    assert.notEqual(await countdown(), initialCountdown, 'live countdown advances');
    await click(grandpa.component_id, 'pause');
    const paused = await waitFor(() => api('/workspace/reminders'), rows => rows[0].status === 'paused', 'paused reminder');
    assert.ok(paused[0].remaining_seconds < 30 && paused[0].remaining_seconds > 20);
    await reload();
    await waitForCards(1);
    const pausedCountdown = await countdown();
    await sleep(1200);
    assert.equal(await countdown(), pausedCountdown, 'paused value survives reload and does not tick');
    await click(grandpa.component_id, 'resume');
    const resumed = await waitFor(() => api('/workspace/reminders'), rows => rows[0].status === 'active', 'resumed reminder');
    assert.ok(Date.parse(resumed[0].due_at) > Date.parse(grandpa.due_at), 'resumed deadline includes paused time');
    t.diagnostic('Verified real 30-second chat countdown, pause/reload, and resumed deadline.');

    await send('remind me to breathe in 3 seconds');
    await send('remind me to look away in 4 seconds');
    await waitForCards(3);
    await waitFor(() => evaluate('return Array.from(document.querySelectorAll("#toastHost .toast")).map(el => el.textContent);'),
        messages => messages.some(text => text === 'Reminder: Breathe') && messages.some(text => text === 'Reminder: Look away'),
        'both due reminder toasts', 10000);
    await waitFor(() => api('/workspace/notifications'), rows => rows.length === 0, 'displayed alerts acknowledged');
    const rows = await api('/workspace/reminders');
    const third = rows.find(row => row.label === 'Look away');
    await click(third.component_id, 'earlier');
    await waitFor(() => api('/workspace/components'), components => components[1].id === third.component_id, 'persisted move');
    await waitFor(() => evaluate(`return document.activeElement?.closest('[data-component-id]')?.dataset.componentId === '${third.component_id}'
        && document.activeElement?.dataset.control === 'earlier';`), Boolean, 'keyboard focus retained after move');
    await sleep(1200);
    assert.equal(await evaluate(`return document.activeElement?.closest('[data-component-id]')?.dataset.componentId === '${third.component_id}';`), true,
        'background polls preserve control focus');
    await click(grandpa.component_id, 'close');
    await waitForCards(2);
    assert.equal((await api('/workspace/reminders')).find(row => row.id === grandpa.id).status, 'active', 'closing does not cancel');
    await reload();
    await waitForCards(2);
    assert.equal((await api('/workspace/components'))[0].visible, false, 'close survives reload');
    assert.deepEqual(await evaluate('return Array.from(document.querySelectorAll(".workspace-card-title")).map(el => el.textContent);'),
        ['Look away', 'Breathe'], 'moved order survives reload');
    await evaluate("document.querySelector('.workspace-closed').open = true; document.querySelector('.workspace-closed button').click(); return true;");
    await waitForCards(3);
    await click(grandpa.component_id, 'pause');
    await waitFor(() => api('/workspace/reminders'), reminders => reminders.find(row => row.id === grandpa.id).status === 'paused', 'pause before restart');
    t.diagnostic('Verified multiple scheduled alerts, acknowledgement, persisted move/close, and restore.');

    for (const width of [320, 375, 760, 1280]) {
        await call('browsingContext.setViewport', { context, viewport: { width, height: 800 } });
        const layout = await evaluate(`await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            const host = document.querySelector('#workspaceComponents'); const send = document.querySelector('#sendBtn').getBoundingClientRect();
            return { width: innerWidth, client: host.clientWidth, scroll: host.scrollWidth, sendRight: send.right,
                controls: Array.from(document.querySelectorAll('.workspace-card-controls')).map(el => el.getBoundingClientRect().right) };`);
        assert.equal(layout.width, width);
        assert.ok(layout.scroll <= layout.client + 1, `widgets overflow at ${width}px`);
        assert.ok(layout.controls.every(right => right <= width), `widget controls clip at ${width}px`);
        assert.ok(layout.sendRight <= width, `composer clips at ${width}px`);
    }

    // Stop delivery, then let a reminder become overdue while the backend is down.
    await evaluate('workspaceRuntime.stop(); return true;');
    await waitFor(() => evaluate('return !workspaceRuntime.busy;'), Boolean, 'poll settled');
    const restartReminder = await api('/workspace/reminders', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: 'Restart recovery', duration_seconds: 2 }) });
    await stopServer();
    await sleep(2200);
    await startServer();
    const pending = await waitFor(() => api('/workspace/notifications'), notifications => notifications.some(n => n.reminder_id === restartReminder.id), 'restart alert');
    assert.equal(pending.filter(n => n.reminder_id === restartReminder.id).length, 1);
    await stopServer();
    await startServer();
    assert.equal((await api('/workspace/notifications')).filter(n => n.reminder_id === restartReminder.id).length, 1, 'second restart does not duplicate');
    assert.equal((await api('/workspace/reminders')).find(row => row.id === grandpa.id).status, 'paused');
    await evaluate('workspaceRuntime.start(); return true;');
    await waitFor(() => evaluate('return Array.from(document.querySelectorAll("#toastHost .toast")).some(el => el.textContent === "Reminder: Restart recovery");'), Boolean, 'recovered notification rendered');
    await waitFor(() => api('/workspace/notifications'), notifications => notifications.length === 0, 'recovered notification acknowledged');
    assert.equal((await api('/workspace/events')).filter(event => event.type === 'reminder.due' && event.reminder_id === restartReminder.id).length, 1);
    t.diagnostic('Verified two actual backend restarts: overdue recovery, no duplicate alert, and paused-state persistence.');

    // Finish the original 30-second reminder's real active countdown after its pauses.
    await click(grandpa.component_id, 'resume');
    await waitFor(() => evaluate('return Array.from(document.querySelectorAll("#toastHost .toast")).some(el => el.textContent === "Reminder: Check on grandpa");'),
        Boolean, 'original 30-second reminder notification', 35000);
    await waitFor(() => api('/workspace/reminders'), reminders => reminders.find(row => row.id === grandpa.id).status === 'due', 'original reminder due');
    await click(grandpa.component_id, 'complete');
    await waitFor(() => api('/workspace/reminders'), reminders => reminders.find(row => row.id === grandpa.id).status === 'completed', 'Done control persists');
    assert.equal((await api('/tasks')).count, 0);
    t.diagnostic('Original grandpa reminder completed its full countdown, displayed an alert, and persisted Done.');

    const jsonOptions = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    await api('/capabilities/timer', jsonOptions('PATCH', { enabled: false }));
    await send('Create a task to call grandpa tomorrow and remind me in 30 minutes');
    const workflow = (await api('/workspace/workflows')).find(row => row.title === 'Call grandpa');
    assert.ok(workflow, 'chat creates a workflow');
    const workflowPath = `/workspace/workflows/${workflow.id}`;
    const linkedTask = workflow.steps[0].result.item_id;
    await waitFor(() => api(workflowPath), row => row.status === 'failed', 'bounded retries exhausted');
    await waitFor(() => evaluate(`return document.querySelector('[data-component-id="${workflow.component_id}"] .workspace-step-error')?.textContent;`),
        text => text?.includes('Enable timers'), 'step failure displayed in workflow panel');
    await stopServer();
    await waitFor(() => evaluate('return document.querySelector("#workspaceComponents").dataset.offline;'),
        value => value === 'true', 'offline widgets retained');
    await startServer();
    const failedAfterRestart = await api(workflowPath);
    assert.equal(failedAfterRestart.status, 'failed');
    assert.equal(failedAfterRestart.steps[0].result.item_id, linkedTask);
    assert.equal(failedAfterRestart.steps[0].attempts, 1);
    await api('/capabilities/timer', jsonOptions('PATCH', { enabled: true }));
    await click(workflow.component_id, 'retry');
    const recovered = await waitFor(() => api(workflowPath), row => row.steps[1].status === 'completed', 'retry failed reminder step');
    assert.equal(recovered.steps[0].attempts, 1, 'retry does not re-create completed task');
    assert.equal(recovered.steps[1].attempts, 4, 'persisted attempts include manual retry');
    assert.equal((await api('/tasks')).tasks.filter(task => task.title === 'Call grandpa').length, 1);
    await reload();
    await waitFor(() => evaluate(`return document.querySelector('[data-component-id="${workflow.component_id}"] .workspace-template-list')?.textContent;`),
        text => text?.includes('wait_for_reminder · waiting'), 'workflow wait survives browser reload');
    for (const width of [320, 375, 760, 1280]) {
        await call('browsingContext.setViewport', { context, viewport: { width, height: 800 } });
        const layout = await evaluate(`await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            const host = document.querySelector('#workspaceComponents'); const card = document.querySelector('[data-component-id="${workflow.component_id}"]');
            return { client: host.clientWidth, scroll: host.scrollWidth, cardRight: card.getBoundingClientRect().right };`);
        assert.ok(layout.scroll <= layout.client + 1 && layout.cardRight <= width, `workflow panel fits ${width}px`);
    }
    await api(`/tasks/${linkedTask}`, jsonOptions('PUT', { status: 'completed' }));
    await waitFor(() => api(workflowPath), row => row.status === 'completed', 'linked task completes workflow');
    assert.equal((await api('/workspace/reminders')).find(row => row.id === recovered.steps[1].result.item_id).status, 'completed');
    await waitFor(() => evaluate(`return document.querySelector('[data-component-id="${workflow.component_id}"] .workspace-status')?.textContent;`),
        text => text === 'completed · 3/3 steps complete', 'completion reflected in status panel');
    t.diagnostic('Workflow failure survived a server restart; UI retry preserved the task, and linked completion finished the workflow.');

    await send('Create a task to buy milk and remind me in 30 seconds');
    const cancel = (await api('/workspace/workflows')).find(row => row.title === 'Buy milk');
    await waitFor(() => evaluate(`return Boolean(document.querySelector('${selector(cancel.component_id, 'cancel')}'));`), Boolean, 'workflow cancel control');
    await click(cancel.component_id, 'cancel');
    const cancelled = await waitFor(() => api(`/workspace/workflows/${cancel.id}`), row => row.status === 'cancelled', 'cancelled workflow');
    assert.equal((await api(`/tasks/${cancelled.steps[0].result.item_id}`)).status, 'pending', 'created task is retained');
    assert.equal((await api('/workspace/reminders')).find(row => row.id === cancelled.steps[1].result.item_id).status, 'cancelled');

    await evaluate('workspaceRuntime.stop(); return true;');
    await waitFor(() => evaluate('return !workspaceRuntime.busy;'), Boolean, 'poll stopped for workflow restart');
    await send('remind me to look away in 5 seconds then create task: Water plants tomorrow');
    const delayed = (await api('/workspace/workflows')).find(row => row.title === 'Water plants');
    assert.equal(delayed.steps[1].status, 'waiting');
    assert.equal((await api('/tasks')).tasks.filter(task => task.title === 'Water plants').length, 0);
    await stopServer();
    await sleep(5100);
    await startServer();
    const delayedResult = await waitFor(() => api(`/workspace/workflows/${delayed.id}`), row => row.status === 'completed', 'deferred workflow resumes after restart');
    const followUp = delayedResult.steps[2].result.item_id;
    assert.ok(followUp);
    await stopServer();
    await startServer();
    assert.equal((await api('/tasks')).tasks.filter(task => task.title === 'Water plants').length, 1);
    assert.equal((await api(`/workspace/workflows/${delayed.id}`)).steps[2].result.item_id, followUp);
    await evaluate('workspaceRuntime.start(); return true;');
    await waitFor(() => evaluate(`return document.querySelector('[data-component-id="${delayed.component_id}"] .workspace-status')?.textContent;`),
        text => text === 'completed · 3/3 steps complete', 'recovered workflow displayed');
    t.diagnostic('Verified UI cancellation and two more server restarts: deferred task executes once after its reminder deadline.');

    const templateDefinition = {
        schema_version: 1, layout: 'stack', permissions: ['workflows.read'],
        nodes: [
            { id: 'title', type: 'text', source: 'title' },
            { id: 'status', type: 'status', source: 'status' },
            { id: 'progress', type: 'progress', source: 'progress' },
            { id: 'steps', type: 'list', source: 'steps' },
        ], actions: [],
    };
    await api('/workspace/templates', jsonOptions('POST', {
        id: 'care-panel', name: 'Care panel', description: 'A declarative care status panel', definition: templateDefinition,
    }));
    const panelInstance = await api('/workspace/templates/care-panel/instances', jsonOptions('POST', {
        data: { title: '<safe text>', status: 'active', progress: 0.5,
            steps: [{ action: 'status', status: 'complete', error: '<safe error>' }] },
    }));
    await evaluate('await workspaceRuntime.refresh(); return true;');
    await waitFor(() => evaluate(`return Boolean(document.querySelector('[data-component-id="${panelInstance.component}"].workspace-template-card'));`),
        Boolean, 'declarative panel displayed');
    assert.equal(await evaluate(`return document.querySelector('[data-component-id="${panelInstance.component}"] .workspace-template-text').textContent;`), '<safe text>');
    assert.equal(await evaluate(`return document.querySelector('[data-component-id="${panelInstance.component}"] progress').value;`), 0.5);
    assert.equal(await evaluate(`return document.querySelector('[data-component-id="${panelInstance.component}"] .workspace-step-error').textContent;`), '<safe error>');
    const panelCard = await api('/workspace/components');
    const panel = panelCard.find(component => component.id === panelInstance.component);
    await api('/workspace/templates/care-panel/versions', jsonOptions('POST', {
        definition: { ...templateDefinition, nodes: templateDefinition.nodes.map(node => node.id === 'title'
            ? { ...node, label: 'Updated panel title' } : node) },
    }));
    await waitFor(() => evaluate(`return Boolean(document.querySelector('[data-component-id="${panel.id}"] [data-control="upgrade"]'));`),
        Boolean, 'template upgrade control');
    await click(panel.id, 'upgrade');
    await waitFor(() => api('/workspace/components'), rows => rows.find(component => component.id === panel.id).template.version === 2,
        'component upgraded to pinned template version');
    await click(panel.id, 'archive');
    await waitFor(() => api('/workspace/components'), rows => rows.find(component => component.id === panel.id).lifecycle === 'archived',
        'component archived');
    assert.equal(await evaluate(`return Boolean(document.querySelector('[data-component-id="${panel.id}"]'));`), false);
    await evaluate(`const button = Array.from(document.querySelectorAll('.workspace-closed button')).find(button => button.textContent.includes('<safe text>')); button.click(); return true;`);
    await waitFor(() => api('/workspace/components'), rows => rows.find(component => component.id === panel.id).lifecycle === 'active',
        'archived component restored');
    await waitFor(() => evaluate(`return Boolean(document.querySelector('[data-component-id="${panel.id}"].workspace-template-card'));`),
        Boolean, 'restored declarative panel displayed');
    t.diagnostic('Verified a versioned declarative panel: safe text-only rendering, progress/list nodes, upgrade, archive, and restore.');
});
