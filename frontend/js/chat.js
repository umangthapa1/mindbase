const MAX_MESSAGE_LENGTH = 10000;

// Mirrors PLACEHOLDER_TITLE_RE in backend/intelligence.py. A title matching this
// is one nobody has meaningfully named yet, so the backend is still free to
// replace it with an LLM-generated one.
const PLACEHOLDER_TITLE_RE = /^(new conv|new chat|untitled|conversation|chat|\d{4}[-/ ])/i;

// How long to wait before each attempt at picking up the generated title. The
// backend produces it in a background task after the stream ends, so there is no
// event to listen for — back off instead of hammering the endpoint.
const TITLE_POLL_DELAYS_MS = [1200, 2500, 4000, 6000];

class ChatManager {
    constructor() {
        this.currentConversationId = null;
        this.conversations = [];
        this.isLoading = false;
        this.messageContextMenu = null;
        this.activeMessageElement = null;
    }

    async initialize() {
        await this.loadConversations();
        await this.loadModels();
        this.updateAgentBadge();
        this.setupMessageInput();
        this.setupMessageContextMenu();
        this.setupCodeBlockCopyButtons();
        // Export button
        const exportBtn = $('#exportConversationBtn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportCurrentConversation());
        }
    }

    setupCodeBlockCopyButtons() {
        if (this.codeCopyButtonsBound) return;
        this.codeCopyButtonsBound = true;

        $('#messagesContainer')?.addEventListener('click', async (event) => {
            const target = event.target instanceof Element ? event.target : null;
            const button = target?.closest('[data-action="copy-code"]');
            if (!button) return;

            const codeBlock = button.closest('pre')?.querySelector('code');
            const text = codeBlock?.textContent?.trim() || '';
            if (!text) {
                toast('Nothing to copy.', 'info');
                return;
            }

            try {
                if (navigator.clipboard?.writeText) {
                    await navigator.clipboard.writeText(text);
                } else {
                    const fallback = document.createElement('textarea');
                    fallback.value = text;
                    fallback.setAttribute('readonly', 'true');
                    fallback.style.position = 'fixed';
                    fallback.style.opacity = '0';
                    document.body.appendChild(fallback);
                    fallback.select();
                    document.execCommand('copy');
                    fallback.remove();
                }

                const originalText = button.textContent;
                button.textContent = 'Copied!';
                button.disabled = true;
                setTimeout(() => {
                    button.textContent = originalText;
                    button.disabled = false;
                }, 1200);

                toast('Code copied.', 'info');
            } catch (err) {
                console.error('Failed to copy code block:', err);
                toast('Could not copy the code.', 'error');
            }
        });
    }

    setupMessageContextMenu() {
        if (this.messageContextMenu) return;

        const menu = document.createElement('div');
        menu.className = 'message-context-menu';
        menu.hidden = true;
        menu.innerHTML = `
            <button type="button" class="message-context-menu-item" data-action="copy">Copy message</button>
        `;

        menu.addEventListener('click', async (event) => {
            const target = event.target instanceof Element ? event.target : null;
            const item = target?.closest('[data-action]');
            if (!item) return;

            const action = item.dataset.action;
            if (action === 'copy') {
                await this.copyActiveMessage();
            }

            this.hideMessageContextMenu();
        });

        document.body.appendChild(menu);
        this.messageContextMenu = menu;

        document.addEventListener('click', (event) => {
            if (!this.messageContextMenu || this.messageContextMenu.hidden) return;
            const target = event.target instanceof Element ? event.target : null;
            if (this.messageContextMenu.contains(event.target)) return;
            if (target?.closest('.message')) return;
            this.hideMessageContextMenu();
        });

        document.addEventListener('contextmenu', (event) => {
            const target = event.target instanceof Element ? event.target : null;
            if (target?.closest('.message') || target?.closest('.message-context-menu')) return;
            this.hideMessageContextMenu();
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                this.hideMessageContextMenu();
            }
        });

        const closeOnScroll = () => this.hideMessageContextMenu();
        $('#messagesContainer')?.addEventListener('scroll', closeOnScroll, { passive: true });
        window.addEventListener('resize', closeOnScroll);
    }

    showMessageContextMenu(messageElement, event) {
        if (!this.messageContextMenu) return;

        this.activeMessageElement = messageElement;
        this.messageContextMenu.hidden = false;
        this.messageContextMenu.classList.add('visible');
        messageElement.classList.add('has-context-menu');

        const menuWidth = 180;
        const menuHeight = 56;
        const padding = 10;
        const x = Math.min(event.clientX, window.innerWidth - menuWidth - padding);
        const y = Math.min(event.clientY, window.innerHeight - menuHeight - padding);

        this.messageContextMenu.style.left = `${Math.max(padding, x)}px`;
        this.messageContextMenu.style.top = `${Math.max(padding, y)}px`;
    }

    hideMessageContextMenu() {
        if (!this.messageContextMenu) return;

        this.messageContextMenu.hidden = true;
        this.messageContextMenu.classList.remove('visible');
        this.messageContextMenu.style.left = '';
        this.messageContextMenu.style.top = '';

        if (this.activeMessageElement) {
            this.activeMessageElement.classList.remove('has-context-menu');
        }

        this.activeMessageElement = null;
    }

    getMessageCopyText(messageElement) {
        const bubble = messageElement?.querySelector('.msg-bubble');
        if (!bubble) return '';

        return (bubble.innerText || bubble.textContent || '')
            .replace(/\n{3,}/g, '\n\n')
            .trim();
    }

    async copyActiveMessage() {
        const text = this.getMessageCopyText(this.activeMessageElement);
        if (!text) {
            toast('Nothing to copy.', 'info');
            return;
        }

        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(text);
            } else {
                const fallback = document.createElement('textarea');
                fallback.value = text;
                fallback.setAttribute('readonly', 'true');
                fallback.style.position = 'fixed';
                fallback.style.opacity = '0';
                document.body.appendChild(fallback);
                fallback.select();
                document.execCommand('copy');
                fallback.remove();
            }

            toast('Message copied.', 'info');
        } catch (err) {
            console.error('Failed to copy message:', err);
            toast('Could not copy the message.', 'error');
        }
    }

    /* ── Agent badge (single source of truth for the active agent) ── */
    updateAgentBadge() {
        const badge = $('#agentBadge');
        if (!badge) return;

        let agent = null;
        try {
            agent = JSON.parse(localStorage.getItem('selectedAgent') || 'null');
        } catch { agent = null; }

        if (agent?.name) {
            badge.innerHTML = '';
            const label = document.createElement('span');
            label.textContent = agent.name;
            badge.appendChild(label);

            const clear = document.createElement('button');
            clear.className = 'agent-clear';
            clear.title = 'Clear active agent — use default';
            clear.setAttribute('aria-label', `Clear agent ${agent.name} and use default`);
            clear.innerHTML = `<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><line x1="3" y1="3" x2="9" y2="9"/><line x1="9" y1="3" x2="3" y2="9"/></svg>`;
            clear.addEventListener('click', () => this.clearAgent());
            badge.appendChild(clear);

            badge.classList.add('visible');
        } else {
            badge.innerHTML = '';
            badge.classList.remove('visible');
        }
    }

    clearAgent() {
        localStorage.removeItem('selectedAgent');
        this.updateAgentBadge();
        toast('Using default model', 'info');
    }

    /* ── Models ── */
    async loadModels() {
        try {
            const data = await API.getModels();
            const sel = $('#modelSelector');
            sel.innerHTML = '<option value="">Default model</option>';
            if (data.models?.length) {
                data.models.forEach(model => {
                    const opt = document.createElement('option');
                    opt.value = model.name;
                    opt.textContent = model.name.split(':')[0];
                    sel.appendChild(opt);
                });
            }
            // Set the selected value to the saved default model from localStorage
            const savedModel = localStorage.getItem('defaultModel');
            if (savedModel) {
                sel.value = savedModel;
            }
            // Log when user changes model selection
            if (!sel.dataset.modelListenerAdded) {
                sel.addEventListener('change', () => {
                    console.log('Model switched to:', sel.value);
                });
                sel.dataset.modelListenerAdded = 'true';
            }
        } catch (err) {
            console.error('Failed to load models:', err);
        }
    }

    /* ── Conversations list ── */
    async loadConversations() {
        // FIX 13: Show loading skeleton while fetching
        const list = $('#conversationsList');
        list.setAttribute('aria-busy', 'true');
        list.innerHTML = `
            <div class="conv-skeleton"></div>
            <div class="conv-skeleton"></div>
            <div class="conv-skeleton"></div>
        `;
        try {
            this.conversations = await API.listConversations();
            this.renderConversations();

            // Automatically select the first conversation if none is selected
            if (this.conversations.length > 0 && this.currentConversationId === null) {
                await this.selectConversation(this.conversations[0].id);
            }
        } catch (err) {
            console.error('Failed to load conversations:', err);
            list.innerHTML = '<p class="conv-empty">Failed to load</p>';
            toast('Could not load conversations.', 'error');
        } finally {
            list.setAttribute('aria-busy', 'false');
        }
    }

    renderConversations() {
        const list = $('#conversationsList');
        list.innerHTML = '';

        if (!this.conversations.length) {
            const empty = document.createElement('p');
            empty.className = 'conv-empty';
            empty.textContent = 'No conversations yet';
            list.appendChild(empty);
            return;
        }

        this.conversations.forEach(conv => {
            const el = document.createElement('div');
            el.className = 'conv-item' + (conv.id === this.currentConversationId ? ' active' : '');
            el.title = conv.title;
            el.textContent = truncate(conv.title, 38);

            el.addEventListener('click', () => this.selectConversation(conv.id));

            // FIX 3: Replace blocking confirm() with inline delete button
            el.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this._showDeleteConfirm(conv.id, el);
            });

            list.appendChild(el);
        });
    }

    // FIX 3: Non-blocking inline delete confirmation
    _showDeleteConfirm(id, el) {
        // Remove any existing confirm UI
        document.querySelectorAll('.conv-delete-confirm').forEach(e => e.remove());

        const confirm = document.createElement('div');
        confirm.className = 'conv-delete-confirm';
        confirm.innerHTML = `
            <span>Delete?</span>
            <button class="btn-confirm-yes">Yes</button>
            <button class="btn-confirm-no">No</button>
        `;

        confirm.querySelector('.btn-confirm-yes').addEventListener('click', (e) => {
            e.stopPropagation();
            confirm.remove();
            this.deleteConversation(id);
        });

        confirm.querySelector('.btn-confirm-no').addEventListener('click', (e) => {
            e.stopPropagation();
            confirm.remove();
        });

        el.appendChild(confirm);
    }

    /* ── Select / load conversation ── */
    async selectConversation(id) {
        this.hideMessageContextMenu();
        this.currentConversationId = id;
        this.renderConversations();
        try {
            const conv = await API.getConversation(id);
            this.displayConversation(conv);
            $('#pageTitle').textContent = conv.title || 'Conversation';
        } catch (err) {
            console.error('Failed to load conversation:', err);
        }
    }

    displayConversation(conversation) {
        this.hideMessageContextMenu();
        this.clearMessages();
        conversation.messages.forEach(msg => this.appendMessage(msg.role, msg.content));
        this.scrollBottom();
    }

    /* ── Create / delete ── */
    async createConversation() {
        try {
            const conv = await API.createConversation();
            this.conversations.unshift(conv);
            this.renderConversations();
            this.currentConversationId = conv.id;
            this.clearMessages(true);
            $('#pageTitle').textContent = conv.title || 'Conversation';
        } catch (err) {
            console.error('Failed to create conversation:', err);
        }
    }

    async deleteConversation(id) {
        try {
            await API.deleteConversation(id);
            this.conversations = this.conversations.filter(c => c.id !== id);
            if (this.currentConversationId === id) {
                this.currentConversationId = null;
                this.clearMessages(true);
                $('#pageTitle').textContent = 'Conversation';
            }
            this.renderConversations();
        } catch (err) {
            console.error('Failed to delete conversation:', err);
        }
    }

    /* ── DOM helpers ── */
    clearMessages(showWelcome = false) {
        this.hideMessageContextMenu();
        const inner = $('#messagesInner');
        inner.innerHTML = `
            <div class="typing-indicator" id="typingIndicator" aria-label="Assistant is typing">
                <div class="msg-avatar" aria-hidden="true">AI</div>
                <div class="typing-dots" aria-hidden="true">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;

        if (showWelcome) {
            const welcome = document.createElement('div');
            welcome.className = 'welcome';
            welcome.id = 'welcomeState';
            welcome.innerHTML = `
                <div class="welcome-logo" aria-hidden="true">
                    <svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="2"  y="2"  width="7" height="7" rx="2" fill="rgba(255,255,255,0.70)"/>
                        <rect x="11" y="2"  width="7" height="7" rx="2" fill="rgba(255,255,255,0.35)"/>
                        <rect x="2"  y="11" width="7" height="7" rx="2" fill="rgba(255,255,255,0.35)"/>
                        <rect x="11" y="11" width="7" height="7" rx="2" fill="rgba(255,255,255,0.18)"/>
                    </svg>
                </div>
                <h2>Mindbase</h2>
                <p>Your AI workspace. Start a conversation below.</p>
            `;
            inner.insertBefore(welcome, inner.firstChild);
        }
    }

    // FIX 7: Merged appendMessage + appendStreamingMessage into one function
    // streaming=true returns the bubble div for live updates; streaming=false returns the message el
    appendMessage(role, content, streaming = false) {
        // Remove welcome state on first real message
        const welcome = $('#welcomeState');
        if (welcome) welcome.remove();

        const inner = $('#messagesInner');
        const typing = $('#typingIndicator');

        const el = document.createElement('div');
        el.className = `message ${role}`;

        const avatarLabel = role === 'user' ? 'You' : 'AI';
        let bubbleHTML = '';
        if (!streaming) {
            bubbleHTML = role === 'assistant'
                ? renderMarkdown(content)
                : `<p>${escapeHTML(content)}</p>`;
        }

        el.innerHTML = `
            <div class="msg-avatar" aria-hidden="true">${avatarLabel}</div>
            <div class="msg-content">
                <div class="msg-bubble">${bubbleHTML}</div>
            </div>
        `;

        el.addEventListener('contextmenu', (event) => {
            event.preventDefault();
            this.showMessageContextMenu(el, event);
        });

        el.addEventListener('click', () => {
            this.hideMessageContextMenu();
        });

        // Syntax highlight code blocks for non-streaming messages
        if (!streaming) {
            el.querySelectorAll('pre code').forEach(block => {
                try { hljs.highlightElement(block); } catch {}
            });
        }

        // Insert before typing indicator
        inner.insertBefore(el, typing);

        return streaming ? el.querySelector('.msg-bubble') : el;
    }

    scrollBottom(behavior = 'auto') {
        const container = $('#messagesContainer');
        if (!container) return;

        requestAnimationFrame(() => {
            if (behavior === 'smooth' && typeof container.scrollTo === 'function') {
                container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
            } else {
                container.scrollTop = container.scrollHeight;
            }
        });
    }

    /* ── Typing indicator ── */
    setTyping(visible) {
        const t = $('#typingIndicator');
        if (t) t.classList.toggle('visible', visible);
        if (visible) this.scrollBottom();
    }

    /* ── Send button state ── */
    setSendLoading(loading) {
        const btn = $('#sendBtn');
        if (!btn) return;
        btn.disabled = loading;
        btn.classList.toggle('loading', loading);
    }

    /* ── Message input ── */
    setupMessageInput() {
        const input = $('#messageInput');
        if (!input || input.dataset.bound) return;
        input.dataset.bound = '1';

        const counter = $('#charCounter');
        const maxHeight = 120;

        const adjustHeight = () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, maxHeight) + 'px';
        };

        input.addEventListener('input', () => {
            adjustHeight();
            this.updateCharCount(input.value.length, counter);
        });

        input.addEventListener('focus', () => {
            input.closest('.composer')?.classList.add('input-focused');
        });

        input.addEventListener('blur', () => {
            input.closest('.composer')?.classList.remove('input-focused');
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        adjustHeight();
    }

    updateCharCount(count, counterElement) {
        if (!counterElement) return;

        if (count <= 8000) {
            counterElement.hidden = true;
            counterElement.classList.remove('limit-warning');
            return;
        }

        counterElement.hidden = false;
        counterElement.textContent = `${count.toLocaleString()} / ${MAX_MESSAGE_LENGTH.toLocaleString()}`;

        if (count > MAX_MESSAGE_LENGTH * 0.95) {
            counterElement.style.color = 'var(--danger)';
            counterElement.classList.add('limit-warning');
        } else if (count > MAX_MESSAGE_LENGTH * 0.9) {
            counterElement.style.color = 'var(--warning)';
            counterElement.classList.add('limit-warning');
        } else {
            counterElement.style.color = 'var(--text-tertiary)';
            counterElement.classList.remove('limit-warning');
        }
    }

    /* ── Send message ── */
    async sendMessage() {
        const input = $('#messageInput');
        const message = input.value.trim();
        if (!message || this.isLoading) return;

        // FIX 4: Enforce max message length
        if (message.length > MAX_MESSAGE_LENGTH) {
            toast(`Message is too long — keep it under ${MAX_MESSAGE_LENGTH.toLocaleString()} characters.`, 'error');
            return;
        }

        if (!this.currentConversationId) {
            toast('Create or select a conversation first.', 'info');
            return;
        }

        input.value = '';
        input.style.height = 'auto';
        this.updateCharCount(0, $('#charCounter'));
        this.isLoading = true;
        this.setTyping(true);
        this.setSendLoading(true);

        // Append user message immediately
        this.appendMessage('user', message);
        this.scrollBottom();

        // Show a provisional title straight away so the sidebar isn't stuck on
        // "New Conversation" while the model works. Deliberately NOT persisted:
        // the backend only auto-generates a title while the stored one still looks
        // like a placeholder, so writing this truncated version to the DB would
        // permanently suppress the real LLM title.
        const userMessageConv = this.conversations.find(c => c.id === this.currentConversationId);
        const awaitingTitle = !!userMessageConv && PLACEHOLDER_TITLE_RE.test(userMessageConv.title || '');
        if (awaitingTitle) {
            userMessageConv.title = message.length > 30 ? message.substring(0, 30) + '...' : message;
            this.renderConversations();
            $('#pageTitle').textContent = userMessageConv.title;
        }

        // Declare streamBubble outside try block so it's accessible in catch
        let streamBubble = null;
        let assistantContent = '';
        let contextHint = null;
        let firstChunk = true;

        try {
            const selectedModel = $('#modelSelector').value;

            for await (const data of API.streamMessage(
                this.currentConversationId,
                message,
                selectedModel || null
            )) {
                // Handle meta / action info
                if (data.meta) {
                    const parts = [];
                    if (data.meta.intent) parts.push(data.meta.intent);
                    if (data.meta.context?.length) parts.push(data.meta.context.join(', '));
                    if (parts.length) contextHint = parts.join(' · ');
                    if (data.meta.actions?.length) {
                        const actionNote = data.meta.actions
                            .filter(a => a.success)
                            .map(a => a.message.replace(/\*\*/g, ''))
                            .join(' · ');
                        if (actionNote) contextHint = (contextHint ? contextHint + ' · ' : '') + actionNote;
                    }
                }

                if (data.chunk) {
                    if (firstChunk) {
                        this.setTyping(false);
                        // FIX 7: Use merged appendMessage with streaming=true
                        streamBubble = this.appendMessage('assistant', '', true);
                        firstChunk = false;
                    }
                    assistantContent += data.chunk;
                    streamBubble.innerHTML = renderMarkdown(assistantContent);
                    this.scrollBottom();
                }
            }

            // Highlight code in final streamed message
            if (streamBubble) {
                streamBubble.querySelectorAll('pre code').forEach(block => {
                    try { hljs.highlightElement(block); } catch {}
                });

                if (contextHint) {
                    const hint = document.createElement('p');
                    hint.style.cssText = 'font-size:11px;color:var(--text-tertiary);margin-top:6px;';
                    hint.textContent = contextHint;
                    streamBubble.appendChild(hint);
                }
            }

        } catch (err) {
            console.error('Failed to send message:', err);
            // Keep any text already received instead of adding a misleading second
            // assistant bubble. The browser console keeps the diagnostic detail.
            if (streamBubble && assistantContent) {
                const notice = document.createElement('p');
                notice.style.cssText = 'font-size:11px;color:var(--text-tertiary);margin-top:6px;';
                notice.textContent = 'Response interrupted before completion.';
                streamBubble.appendChild(notice);
                toast('The response was interrupted. Your partial reply was kept.', 'error');
            } else {
                this.appendMessage('assistant', 'Something went wrong. Please try again.');
            }
        } finally {
            this.isLoading = false;
            this.setTyping(false);
            this.setSendLoading(false);
            input.focus();
        }

        // The backend generates the real title in a background task once the stream
        // finishes, so poll briefly for it and swap out the provisional one.
        if (awaitingTitle) {
            await this.pollForGeneratedTitle(this.currentConversationId);
        }
    }

    /**
     * Wait for the backend's LLM-generated title and adopt it.
     * Gives up quietly after TITLE_POLL_DELAYS_MS is exhausted — the provisional
     * title stays, which is the same outcome as before auto-titling existed.
     */
    async pollForGeneratedTitle(conversationId) {
        for (const delay of TITLE_POLL_DELAYS_MS) {
            await new Promise(r => setTimeout(r, delay));

            // The user may have switched or deleted the conversation while we waited.
            if (this.currentConversationId !== conversationId) return;

            let title;
            try {
                // Metadata only — cheaper than /chat/conversations/{id}, which also
                // returns every message in the conversation.
                const list = await API.listConversations();
                title = list.find(c => c.id === conversationId)?.title;
            } catch {
                continue; // transient; try again on the next tick
            }

            if (!title || PLACEHOLDER_TITLE_RE.test(title)) continue;

            const conv = this.conversations.find(c => c.id === conversationId);
            if (conv) conv.title = title;
            this.renderConversations();
            if (this.currentConversationId === conversationId) {
                $('#pageTitle').textContent = title;
            }
            return;
        }
    }

    async exportCurrentConversation() {
        if (!this.currentConversationId) {
            toast('No conversation to export.', 'info');
            return;
        }

        try {
            const conversation = await API.getConversation(this.currentConversationId);
            if (!conversation || !conversation.messages) {
                toast('Conversation data not available.', 'error');
                return;
            }

            // Build the text content
            let text = `Conversation: ${conversation.title || 'Untitled'}\n`;
            text += `Exported on: ${new Date().toLocaleString()}\n`;
            text += '='.repeat(50) + '\n\n';

            conversation.messages.forEach(msg => {
                const role = msg.role === 'user' ? 'You' : 'AI';
                const msgDate = msg.created_at || msg.timestamp;
                const timestamp = msgDate ? new Date(msgDate).toLocaleString() : '';
                text += `[${role}]${timestamp ? ` ${timestamp}` : ''}\n`;
                text += `${msg.content}\n\n`;
            });

            // Create a blob and trigger download
            const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `conversation-${this.currentConversationId}-${new Date().toISOString().slice(0,10)}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Failed to export conversation:', err);
            toast('Failed to export conversation.', 'error');
        }
    }
}

/* ── Small utility not in utils.js ── */
function escapeHTML(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

const chatManager = new ChatManager();
