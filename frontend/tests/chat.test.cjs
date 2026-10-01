const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../js/chat.js'), 'utf8');

function deferred() {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}

// Exercise the real ChatManager lifecycle. Only its leaf DOM operations are
// replaced; this is deliberately not a DOM implementation or a copied controller.
function fixture(api = {}) {
    const elements = {
        '#messageInput': { value: 'Hello', style: {}, focus() { this.focused = true; } },
        '#modelSelector': { value: 'fixture-model' },
        '#pageTitle': { textContent: '' },
        '#typingIndicator .typing-label': { textContent: '' },
        '#typingIndicator': { classList: { toggle(_, value) { state.typing = value; } } },
        '#sendBtn': { disabled: false, classList: { toggle() {} } },
    };
    const state = { messages: [], typing: false, toasts: [], polls: [] };
    const context = vm.createContext({
        API: api,
        $: selector => elements[selector] || null,
        document: {
            querySelector: selector => elements[selector] || null,
            createElement: () => ({ style: {}, textContent: '' }),
        },
        console: { error() {} },
        renderMarkdown: text => text,
        toast: (...args) => state.toasts.push(args),
        setTimeout,
    });
    vm.runInContext(source, context, { filename: 'chat.js' });
    const chat = vm.runInContext('chatManager', context);
    chat.hideMessageContextMenu = () => {};
    chat.renderConversations = () => {};
    chat.scrollBottom = () => {};
    chat.clearMessages = () => { state.messages = []; state.typing = false; };
    chat.appendMessage = (role, content, streaming = false) => {
        const bubble = { innerHTML: content, children: [], querySelectorAll: () => [],
            appendChild(child) { this.children.push(child); } };
        state.messages.push({ role, bubble, streaming });
        return bubble;
    };
    chat.pollForGeneratedTitle = async id => { state.polls.push(id); };
    chat.currentConversationId = 'A';
    chat.conversations = [{ id: 'A', title: 'Alpha' }, { id: 'B', title: 'Beta' }];
    return { chat, state, elements };
}

const conversation = (id, content = `${id} history`) => ({
    id, title: id === 'A' ? 'Alpha' : 'Beta', messages: [{ role: 'assistant', content }],
});
const contents = state => state.messages.map(message => message.bubble.innerHTML);
const tick = () => new Promise(resolve => setImmediate(resolve));

function streamFixture() {
    const events = [];
    const calls = [];
    let waiting;
    const api = {
        getConversation: async id => conversation(id),
        async *streamMessage(...args) {
            calls.push(args);
            while (true) {
                if (!events.length) { waiting = deferred(); await waiting.promise; }
                const event = events.shift();
                if (event === null) return;
                if (event instanceof Error) throw event;
                yield event;
            }
        },
    };
    const ui = fixture(api);
    return { ...ui, api, calls, async push(event) {
        events.push(event);
        waiting?.resolve();
        await tick();
    } };
}

test('latest conversation selection wins when A resolves after B', async () => {
    const a = deferred(), b = deferred();
    const { chat, state, elements } = fixture({ getConversation: id => id === 'A' ? a.promise : b.promise });
    const first = chat.selectConversation('A');
    const second = chat.selectConversation('B');
    b.resolve(conversation('B'));
    await second;
    a.resolve(conversation('A'));
    await first;
    assert.equal(chat.currentConversationId, 'B');
    assert.equal(elements['#pageTitle'].textContent, 'Beta');
    assert.deepEqual(contents(state), ['B history']);
});

test('A → B → A ignores the older fetch for the same ID', async () => {
    const oldA = deferred(), b = deferred(), newA = deferred();
    const pending = [oldA, b, newA];
    const { chat, state } = fixture({ getConversation: () => pending.shift().promise });
    const requests = [chat.selectConversation('A'), chat.selectConversation('B'), chat.selectConversation('A')];
    newA.resolve(conversation('A', 'latest A'));
    await requests[2];
    oldA.resolve(conversation('A', 'stale A'));
    b.resolve(conversation('B'));
    await Promise.all(requests);
    assert.deepEqual(contents(state), ['latest A']);
});

test('selection clears the previous view and blocks sends until history is ready', async () => {
    const pending = deferred();
    let sends = 0;
    const { chat, state, elements } = fixture({
        getConversation: () => pending.promise,
        async *streamMessage() { sends++; },
    });
    chat.appendMessage('assistant', 'A history');
    const selection = chat.selectConversation('B');
    assert.deepEqual(contents(state), []);
    assert.equal(elements['#sendBtn'].disabled, true);
    await chat.sendMessage();
    assert.equal(sends, 0);
    assert.equal(elements['#messageInput'].value, 'Hello');
    pending.resolve(conversation('B'));
    await selection;
    assert.equal(elements['#sendBtn'].disabled, false);
});

test('a new conversation invalidates an older selection', async () => {
    const pending = deferred();
    const { chat, state, elements } = fixture({
        getConversation: () => pending.promise,
        createConversation: async () => ({ id: 'C', title: 'New Conversation' }),
    });
    const selection = chat.selectConversation('A');
    await chat.createConversation();
    pending.resolve(conversation('A'));
    await selection;
    assert.equal(chat.currentConversationId, 'C');
    assert.equal(elements['#pageTitle'].textContent, 'New Conversation');
    assert.deepEqual(contents(state), []);
});

for (const query of ['What is on my calendar?', 'List each task', 'Show my tasks', 'Create a meeting tomorrow']) {
    test(`typing stays neutral before backend metadata: ${query}`, async () => {
        const ui = streamFixture();
        ui.elements['#messageInput'].value = query;
        const sending = ui.chat.sendMessage();
        assert.equal(ui.elements['#typingIndicator .typing-label'].textContent, 'Thinking…');
        await ui.push({ meta: { context: ['calendar'], actions: [] } });
        assert.equal(ui.elements['#typingIndicator .typing-label'].textContent, 'Checking calendar…');
        await ui.push(null);
        await sending;
        assert.equal(ui.state.typing, false);
        assert.equal(ui.elements['#sendBtn'].disabled, false);
    });
}

test('a stale failed fetch cannot clear the newly selected conversation', async () => {
    const pending = deferred();
    const { chat, state, elements } = fixture({
        getConversation: id => id === 'A' ? pending.promise : Promise.resolve(conversation(id)),
    });
    const selection = chat.selectConversation('A');
    await chat.selectConversation('B');
    pending.reject(new Error('stale failure'));
    await selection;
    assert.equal(chat.currentConversationId, 'B');
    assert.deepEqual(contents(state), ['B history']);
    assert.deepEqual(state.toasts, []);
    assert.equal(elements['#sendBtn'].disabled, false);
});

test('a failed selected fetch clears its ID and releases loading state for retry', async () => {
    const { chat, state, elements } = fixture({
        getConversation: async () => { throw new Error('fixture failure'); },
    });
    await chat.selectConversation('B');
    assert.equal(chat.currentConversationId, null);
    assert.equal(chat.isConversationLoading, false);
    assert.equal(elements['#sendBtn'].disabled, false);
    assert.deepEqual(contents(state), []);
    assert.equal(state.toasts.length, 1);
});

test('late creation is listed but cannot replace a newer selection', async () => {
    const pending = deferred();
    const { chat, state } = fixture({
        getConversation: async id => conversation(id),
        createConversation: () => pending.promise,
    });
    const creation = chat.createConversation();
    await chat.selectConversation('B');
    pending.resolve({ id: 'C', title: 'New Conversation' });
    await creation;
    assert.equal(chat.currentConversationId, 'B');
    assert.deepEqual(contents(state), ['B history']);
    assert.equal(chat.conversations[0].id, 'C');
});

test('deleting a loading conversation invalidates its pending history fetch', async () => {
    const pending = deferred();
    const { chat, state, elements } = fixture({
        getConversation: () => pending.promise,
        deleteConversation: async () => {},
    });
    const selection = chat.selectConversation('A');
    await chat.deleteConversation('A');
    pending.resolve(conversation('A'));
    await selection;
    assert.equal(chat.currentConversationId, null);
    assert.deepEqual(contents(state), []);
    assert.equal(elements['#pageTitle'].textContent, 'Conversation');
    assert.equal(elements['#sendBtn'].disabled, false);
});

test('normal streaming combines chunks, metadata hints, and releases loading state', async () => {
    const ui = streamFixture();
    const sending = ui.chat.sendMessage();
    assert.equal(ui.chat.isLoading, true);
    await ui.push({ meta: { context: ['notes'] } });
    await ui.push({ chunk: 'First ' });
    await ui.push({ chunk: 'answer' });
    await ui.push(null);
    await sending;
    assert.deepEqual(ui.calls, [['A', 'Hello', 'fixture-model']]);
    assert.deepEqual(contents(ui.state), ['Hello', 'First answer']);
    assert.equal(ui.state.messages[1].bubble.children[0].textContent, 'Used notes');
    assert.equal(ui.chat.isLoading, false);
    assert.equal(ui.elements['#messageInput'].focused, true);
});

for (const withFirstChunk of [false, true]) {
    test(`switching chats isolates stream metadata, chunks and completion (first chunk: ${withFirstChunk})`, async () => {
        const ui = streamFixture();
        ui.chat.conversations[0].title = 'New Conversation';
        const sending = ui.chat.sendMessage();
        if (withFirstChunk) await ui.push({ chunk: 'A partial' });
        await ui.chat.selectConversation('B');
        await ui.push({ meta: { context: ['calendar'] } });
        await ui.push({ chunk: 'A answer' });
        await ui.push(null);
        await sending;
        assert.deepEqual(contents(ui.state), ['B history']);
        assert.equal(ui.elements['#pageTitle'].textContent, 'Beta');
        assert.equal(ui.elements['#typingIndicator .typing-label'].textContent, 'Thinking…');
        assert.equal(ui.elements['#messageInput'].focused, undefined);
        assert.deepEqual(ui.state.polls, ['A']);
        assert.equal(ui.elements['#sendBtn'].disabled, false);
    });
}

for (const withFirstChunk of [false, true]) {
    test(`an offscreen stream error never adds a failure bubble or toast to B (partial: ${withFirstChunk})`, async () => {
        const ui = streamFixture();
        const sending = ui.chat.sendMessage();
        if (withFirstChunk) await ui.push({ chunk: 'A partial' });
        await ui.chat.selectConversation('B');
        await ui.push(new Error('fixture failure'));
        await sending;
        assert.deepEqual(contents(ui.state), ['B history']);
        assert.deepEqual(ui.state.toasts, []);
        assert.equal(ui.chat.isLoading, false);
    });
}

test('stream completion does not enable sending while a different history is loading', async () => {
    const ui = streamFixture();
    const sending = ui.chat.sendMessage();
    const pending = deferred();
    ui.api.getConversation = () => pending.promise;
    const selection = ui.chat.selectConversation('B');
    await ui.push(null);
    await sending;
    assert.equal(ui.elements['#sendBtn'].disabled, true);
    pending.resolve(conversation('B'));
    await selection;
    assert.equal(ui.elements['#sendBtn'].disabled, false);
});

test('an interrupted visible response retains its partial answer in one bubble', async () => {
    const ui = streamFixture();
    const sending = ui.chat.sendMessage();
    await ui.push({ chunk: 'Partial answer' });
    await ui.push(new Error('fixture failure'));
    await sending;
    assert.deepEqual(contents(ui.state), ['Hello', 'Partial answer']);
    assert.equal(ui.state.messages[1].bubble.children[0].textContent, 'Response interrupted before completion.');
    assert.equal(ui.state.toasts.length, 1);
    assert.equal(ui.state.typing, false);
    assert.equal(ui.elements['#sendBtn'].disabled, false);
});

test('returning to the origin during streaming refreshes its saved answer on completion', async () => {
    const ui = streamFixture();
    const sending = ui.chat.sendMessage();
    await ui.push({ chunk: 'A partial' });
    await ui.chat.selectConversation('B');
    await ui.chat.selectConversation('A');
    ui.api.getConversation = async id => conversation(id, 'A complete answer');
    await ui.push({ chunk: ' rest' });
    await ui.push(null);
    await sending;
    assert.equal(ui.chat.currentConversationId, 'A');
    assert.deepEqual(contents(ui.state), ['A complete answer']);
    assert.equal(ui.state.typing, false);
});
