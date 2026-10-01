const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const { once } = require('node:events');
const { mkdtempSync, readFileSync, writeFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { test } = require('node:test');
const { pathToFileURL } = require('node:url');

const firefox = process.env.FIREFOX_BIN || 'firefox';
const available = spawnSync(firefox, ['--version'], { timeout: 10000 }).status === 0;

test('main chat fits mobile widths with long model names and code blocks', {
    skip: !available && 'Firefox is not installed; no packages are needed for the VM tests',
    timeout: 45000,
}, async t => {
    const dir = mkdtempSync(join(tmpdir(), 'mindbase-layout-'));
    const prefs = {
        'browser.shell.checkDefaultBrowser': false,
        'browser.startup.page': 0,
        'browser.startup.homepage': 'about:blank',
        'browser.newtabpage.enabled': false,
        // Measure final layout, not the entrance animation's fractional scale.
        'ui.prefersReducedMotion': 1,
        'browser.safebrowsing.phishing.enabled': false,
        'browser.safebrowsing.malware.enabled': false,
        'datareporting.policy.dataSubmissionEnabled': false,
        'toolkit.telemetry.enabled': false,
        'network.prefetch-next': false,
        'network.dns.disablePrefetch': true,
        // This isolated browser must not contact real services, even for its
        // built-in background requests. The fixture itself has no remote assets.
        'network.proxy.type': 1,
        'network.proxy.http': '127.0.0.1',
        'network.proxy.http_port': 9,
        'network.proxy.ssl': '127.0.0.1',
        'network.proxy.ssl_port': 9,
        'network.proxy.no_proxies_on': 'localhost, 127.0.0.1',
    };
    writeFileSync(join(dir, 'user.js'), Object.entries(prefs)
        .map(([key, value]) => `user_pref(${JSON.stringify(key)}, ${JSON.stringify(value)});`).join('\n'));
    const css = readFileSync(join(__dirname, '../css/globals.css'), 'utf8').replace(/^@import.*$/gm, '');
    const html = readFileSync(join(__dirname, '../index.html'), 'utf8')
        .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
        .replace(/<link\b[^>]*>/gi, '')
        .replace('</head>', `<style>${css}</style></head>`);
    const file = join(dir, 'fixture.html');
    writeFileSync(file, html);

    const browser = spawn(firefox, ['--headless', '--no-remote', '--profile', dir,
        '--remote-debugging-port', '0', 'about:blank'], { stdio: ['ignore', 'pipe', 'pipe'] });
    t.after(async () => {
        if (browser.exitCode === null && browser.signalCode === null) {
            browser.kill('SIGKILL');
            await once(browser, 'exit');
        }
        rmSync(dir, { recursive: true, force: true });
    });
    const endpoint = await new Promise((resolve, reject) => {
        let output = '';
        const timeout = setTimeout(() => reject(new Error(`Firefox startup timed out: ${output}`)), 15000);
        const listen = chunk => {
            output += chunk;
            const match = output.match(/WebDriver BiDi listening on (ws:\/\/\S+)/);
            if (match) { clearTimeout(timeout); resolve(`${match[1]}/session`); }
        };
        browser.stderr.on('data', listen);
        browser.stdout.on('data', listen);
        browser.once('error', err => { clearTimeout(timeout); reject(err); });
        browser.once('exit', code => { clearTimeout(timeout); reject(new Error(`Firefox exited ${code}: ${output}`)); });
    });
    const ws = new WebSocket(endpoint);
    t.after(() => ws.close());
    await once(ws, 'open');
    let nextId = 0;
    const requests = new Map();
    ws.addEventListener('message', ({ data }) => {
        const message = JSON.parse(data);
        const request = requests.get(message.id);
        if (!request) return;
        requests.delete(message.id);
        if (message.type === 'error') request.reject(new Error(JSON.stringify(message)));
        else request.resolve(message.result);
    });
    const call = (method, params) => new Promise((resolve, reject) => {
        const id = ++nextId;
        requests.set(id, { resolve, reject });
        ws.send(JSON.stringify({ id, method, params }));
    });
    await call('session.new', { capabilities: {} });
    const { context } = await call('browsingContext.create', { type: 'tab' });
    await call('browsingContext.navigate', { context, url: pathToFileURL(file).href, wait: 'complete' });
    const evaluate = async expression => {
        const result = await call('script.evaluate', { expression, target: { context }, awaitPromise: true });
        assert.equal(result.type, 'success', JSON.stringify(result));
        return JSON.parse(result.result.value);
    };
    await evaluate(`(() => {
        document.querySelector('#modelSelector').innerHTML = '<option>fixture-reasoning-model-with-long-name:32b</option>';
        document.querySelector('#pageTitle').textContent = 'A long conversation title in the main chat';
        document.querySelector('#messagesInner').innerHTML = '<div class="message assistant"><div class="msg-avatar">AI</div><div class="msg-content"><div class="msg-bubble"><p>A code example</p><pre><code>' + 'x'.repeat(250) + '</code></pre></div></div></div>';
        return JSON.stringify(true);
    })()`);
    const sizes = [320, 375, 390, 760, 1280].flatMap(width => [[width, false], [width, true]]);
    for (const [width, agent] of sizes) {
        await call('browsingContext.setViewport', { context, viewport: { width, height: 800 } });
        const layout = await evaluate(`(async () => {
            // Firefox may acknowledge the viewport before its next layout frame.
            await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            const badge = document.querySelector('#agentBadge');
            badge.classList.toggle('visible', ${agent});
            badge.innerHTML = '<span>Long fixture agent name</span><button class="agent-clear">×</button>';
            const rect = selector => {
                const r = document.querySelector(selector).getBoundingClientRect();
                return { left: r.left, right: r.right, width: r.width };
            };
            const area = document.querySelector('.messages-area');
            const pre = document.querySelector('pre');
            return JSON.stringify({ width: innerWidth, header: rect('.header'),
                menu: rect('.mobile-menu-btn'), model: rect('#modelSelector'),
                controls: rect('.header-controls'), export: rect('#exportConversationBtn'),
                agentClear: rect('.agent-clear'),
                send: rect('#sendBtn'), bubble: rect('.msg-bubble'),
                areaClient: area.clientWidth, areaScroll: area.scrollWidth,
                preClient: pre.clientWidth, preScroll: pre.scrollWidth });
        })()`);
        t.diagnostic(`${width}px, agent ${agent}: model width ${layout.model.width.toFixed(1)}, export right ${layout.export.right}, messages ${layout.areaScroll}/${layout.areaClient}`);
        assert.equal(layout.width, width, 'requested viewport has settled');
        assert.ok(layout.model.left >= 0 && layout.export.right <= width, `header controls clipped at ${width}px`);
        assert.ok(layout.model.width >= 60, `model selector too narrow at ${width}px`);
        if (agent) assert.ok(layout.agentClear.width >= 16 && layout.agentClear.right <= layout.model.left,
            `agent clear control clipped at ${width}px`);
        assert.ok(layout.send.left >= 0 && layout.send.right <= width, `send button clipped at ${width}px`);
        assert.ok(layout.areaScroll <= layout.areaClient + 1, `messages overflow horizontally at ${width}px`);
        assert.ok(layout.preScroll > layout.preClient, 'long code remains independently scrollable');
    }
});
