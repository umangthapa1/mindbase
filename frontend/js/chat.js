const MAX_MESSAGE_LENGTH = 10000;

class ChatManager {
    constructor() {
        this.currentConversationId = null;
        this.conversations = [];
        this.isLoading = false;
    }

    setupMessageInput() {
        const input = $('#messageInput');
        if (!input) return;

        // Auto-resize textarea as user types
        const adjustHeight = () => {
            input.style.height = 'auto';
            input.style.height = (input.scrollHeight) + 'px';
        };

        // Input event for auto-resizing
        input.addEventListener('input', () => {
            // Limit height to prevent excessive growth
            if (input.scrollHeight <= 120) { // Max 4 lines approx
                adjustHeight();
            }

            // Update character counter if implemented
            this.updateCharCount && this.updateCharCount(input.value.length);
        });

        // Focus events for enhanced styling
        input.addEventListener('focus', () => {
            const composer = input.closest('.composer');
            if (composer) {
                composer.classList.add('input-focused');
            }
        });

        input.addEventListener('blur', () => {
            const composer = input.closest('.composer');
            if (composer) {
                composer.classList.remove('input-focused');
            }
        });

        // Prevent form submission on Enter (we handle it separately)
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }

    async initialize() {
        await this.loadConversations();
        await this.loadModels();
        this.updateAgentBadge();
        this.setupMessageInput();
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

    /* ── Message input enhancements ── */
    setupMessageInput() {
        const input = $('#messageInput');
        if (!input) return;

        // Create character counter element
        const counter = document.createElement('div');
        counter.className = 'char-counter';
        counter.textContent = '0/10000';
        input.parentNode.insertBefore(counter, input.nextSibling);

        // Auto-resize textarea as user types
        const adjustHeight = () => {
            input.style.height = 'auto';
            input.style.height = (input.scrollHeight) + 'px';
        };

        // Input event for auto-resizing
        input.addEventListener('input', () => {
            // Limit height to prevent excessive growth
            if (input.scrollHeight <= 120) { // Max 4 lines approx
                adjustHeight();
            }

            // Update character counter
            this.updateCharCount(input.value.length, counter);
        });

        // Focus events for enhanced styling
        input.addEventListener('focus', () => {
            const composer = input.closest('.composer');
            if (composer) {
                composer.classList.add('input-focused');
            }
        });

        input.addEventListener('blur', () => {
            const composer = input.closest('.composer');
            if (composer) {
                composer.classList.remove('input-focused');
            }
        });

        // Prevent form submission on Enter (we handle it separately)
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }

    updateCharCount(count, counterElement) {
        if (!counterElement) return;

        const maxLength = 10000;
        const percentage = (count / maxLength) * 100;

        counterElement.textContent = `${count}/${maxLength}`;

        // Change color based on length
        if (count > maxLength * 0.9) {
            counterElement.classList.add('limit-warning');
            if (count > maxLength) {
                counterElement.style.color = 'var(--danger)';
            } else {
                counterElement.style.color = 'var(--warning)';
            }
        } else if (count > maxLength * 0.75) {
            counterElement.classList.add('limit-warning');
            counterElement.style.color = 'var(--warning)';
        } else {
            counterElement.classList.remove('limit-warning');
            counterElement.style.color = 'var(--text-tertiary)';
        }

        // Prevent typing past limit
        if (count > maxLength) {
            this.showToast(`Message is too long — keep it under ${maxLength.toLocaleString()} characters.`, 'error');
            // Truncate to max length
            const truncated = this.conversations.find(c => c.id === this.currentConversationId)?.messages.slice(0, -1) || [];
            // Note: Actual truncation would happen in sendMessage validation
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
        // FIX 10: Reset auto-resize height
        input.style.height = 'auto';
        this.isLoading = true;
        this.setTyping(true);
        this.setSendLoading(true);

        // Append user message immediately
        this.appendMessage('user', message);
        this.scrollBottom();

        // If conversation title is still default, set it based on user message
        const userMessageConv = this.conversations.find(c => c.id === this.currentConversationId);
        if (userMessageConv && (userMessageConv.title === 'New Conversation' || userMessageConv.title === 'New conversation')) {
            const title = message.length > 30 ? message.substring(0, 30) + '...' : message;
            try {
                await API.updateConversation(this.currentConversationId, title);
                userMessageConv.title = title;
                this.renderConversations();
                $('#pageTitle').textContent = title;
            } catch (e) {
                console.error('Failed to update conversation title:', e);
            }
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

        // FIX 8: Update conversation title locally instead of reloading all conversations
        // Only update if the title is still the default (indicating we haven't updated it yet)
        const convToUpdate = this.conversations.find(c => c.id === this.currentConversationId);
        if (convToUpdate && (convToUpdate.title === 'New Conversation' || convToUpdate.title === 'New conversation')) {
            try {
                const updated = await API.getConversation(this.currentConversationId);
                convToUpdate.title = updated.title;
                this.renderConversations();
                $('#pageTitle').textContent = updated.title || 'Conversation';
            } catch {
                // Non-critical — title just won't update in sidebar
            }
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
