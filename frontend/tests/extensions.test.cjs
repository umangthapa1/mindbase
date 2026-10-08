const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

test('settings exposes controlled extension management without executable package fields', () => {
    const source = readFileSync(join(__dirname, '../pages/settings.html'), 'utf8');
    assert.match(source, /id="extensionManifest"/);
    assert.match(source, /id="extensionGrants"/);
    assert.match(source, /Validate and install/);
    assert.match(source, /data-extension-action/);
    assert.doesNotMatch(source, /eval\s*\(/);
    assert.match(source, /declarative packs/);
});

test('extension API helpers encode identifiers and send explicit grants', async () => {
    const calls = [];
    const context = vm.createContext({ fetch: async (...args) => {
        calls.push(args); return { ok: true, json: async () => ({}) };
    } });
    vm.runInContext(readFileSync(join(__dirname, '../js/api.js'), 'utf8'), context);
    await vm.runInContext('API.installWorkspaceExtension({id:"pack"}, ["workflows.read"])', context);
    await vm.runInContext('API.actOnWorkspaceExtension("pack/id", "rollback", 2)', context);
    assert.equal(calls[0][0], '/api/workspace/extensions');
    assert.deepEqual(JSON.parse(calls[0][1].body), { manifest: { id: 'pack' }, grant_permissions: ['workflows.read'] });
    assert.equal(calls[1][0], '/api/workspace/extensions/pack%2Fid/actions');
    assert.deepEqual(JSON.parse(calls[1][1].body), { action: 'rollback', version: 2 });
});
