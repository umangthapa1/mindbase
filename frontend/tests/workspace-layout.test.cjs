const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const { once } = require('node:events');
const { mkdtempSync, readFileSync, writeFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { test } = require('node:test');
const { pathToFileURL } = require('node:url');

const firefox = process.env.FIREFOX_BIN || 'firefox';
const pagesDir = join(__dirname, '../pages');
const pages = [
    'agents.html', 'automations.html', 'calendar.html', 'dashboard.html',
    'documents.html', 'email.html', 'memory.html', 'notes.html',
    'research.html', 'settings.html', 'tasks.html',
];
const available = spawnSync(firefox, ['--version'], { timeout: 10000 }).status === 0;

function makeFixture(dir, name, globals, pageTheme) {
    const source = readFileSync(join(pagesDir, name), 'utf8')
        .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
        .replace(/<link\b[^>]*>/gi, '')
        .replace('</head>', `<style>${globals}</style><style>${pageTheme}</style></head>`)
        .replace(/<body([^>]*)>/i, '<body$1 class="has-app-dock">\n<div class="dock--fixed" aria-hidden="true"></div>');
    const file = join(dir, name);
    writeFileSync(file, source);
    return file;
}

test('secondary workspace pages stay usable across desktop and narrow widths', {
    skip: !available && 'Firefox is not installed; no packages are needed for the static fixture check',
    timeout: 60000,
}, async t => {
    const dir = mkdtempSync(join(tmpdir(), 'mindbase-workspace-layout-'));
    const prefs = {
        'browser.shell.checkDefaultBrowser': false,
        'browser.startup.page': 0,
        'browser.startup.homepage': 'about:blank',
        'browser.newtabpage.enabled': false,
        'ui.prefersReducedMotion': 1,
        'browser.safebrowsing.phishing.enabled': false,
        'browser.safebrowsing.malware.enabled': false,
        'datareporting.policy.dataSubmissionEnabled': false,
        'toolkit.telemetry.enabled': false,
        'network.prefetch-next': false,
        'network.dns.disablePrefetch': true,
        'network.proxy.type': 1,
        'network.proxy.http': '127.0.0.1',
        'network.proxy.http_port': 9,
        'network.proxy.ssl': '127.0.0.1',
        'network.proxy.ssl_port': 9,
        'network.proxy.no_proxies_on': 'localhost, 127.0.0.1',
    };
    writeFileSync(join(dir, 'user.js'), Object.entries(prefs)
        .map(([key, value]) => `user_pref(${JSON.stringify(key)}, ${JSON.stringify(value)});`).join('\n'));
    const globals = readFileSync(join(__dirname, '../css/globals.css'), 'utf8').replace(/^@import.*$/gm, '');
    const pageTheme = readFileSync(join(pagesDir, 'page-theme.css'), 'utf8');
    const fixtures = pages.map(name => makeFixture(dir, name, globals, pageTheme));

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
    const evaluate = async expression => {
        const result = await call('script.evaluate', { expression, target: { context }, awaitPromise: true });
        assert.equal(result.type, 'success', JSON.stringify(result));
        return JSON.parse(result.result.value);
    };

    for (const file of fixtures) {
        await call('browsingContext.navigate', { context, url: pathToFileURL(file).href, wait: 'complete' });
        for (const width of [390, 760, 1280]) {
            await call('browsingContext.setViewport', { context, viewport: { width, height: 800 } });
            const layout = await evaluate(`(async () => {
                await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                const rect = el => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, width: r.width }; };
                const controls = [...document.querySelectorAll('.btn, input, select, textarea')]
                    .filter(el => getComputedStyle(el).display !== 'none').map(rect);
                return JSON.stringify({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
                    heading: !!document.querySelector('.page-title'), controls });
            })()`);
            assert.equal(layout.width, width, `${file} viewport settled`);
            assert.ok(layout.heading, `${file} has a page heading`);
            assert.ok(layout.scrollWidth <= width + 1,
                `${file} has no horizontal page overflow at ${width}px (${layout.scrollWidth}px)`);
            for (const control of layout.controls) {
                assert.ok(control.left >= -1 && control.right <= width + 1,
                    `${file} control is clipped at ${width}px (${control.left}..${control.right})`);
            }
        }
    }
});
