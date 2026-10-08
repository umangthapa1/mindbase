const API_BASE = '/api';

class API {
    static async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
            },
            ...options,
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `API Error: ${response.status}`);
        }

        return response;
    }

    // Conversations
    static async createConversation(title = 'New Conversation') {
        const response = await this.request('/chat/conversations', {
            method: 'POST',
            body: JSON.stringify({ title }),
        });
        return response.json();
    }

    static async listConversations() {
        const response = await this.request('/chat/conversations');
        return response.json();
    }

    static async getConversation(conversationId) {
        const response = await this.request(`/chat/conversations/${conversationId}`);
        return response.json();
    }

    static async updateConversation(conversationId, title) {
        const response = await this.request(`/chat/conversations/${conversationId}`, {
            method: 'PUT',
            body: JSON.stringify({ title }),
        });
        return response.json();
    }

    static async deleteConversation(conversationId) {
        const response = await this.request(`/chat/conversations/${conversationId}`, {
            method: 'DELETE',
        });
        return response.json();
    }

    // Messages
    // Per-browser preferences from the Settings page, sent with every chat turn.
    // Anything unset or unparseable is omitted so the backend applies its default.
    static getChatOptions() {
        const opts = {};
        try {
            const agent = JSON.parse(localStorage.getItem('selectedAgent') || 'null');
            if (agent?.prompt) opts.agent_prompt = agent.prompt;
        } catch (_) { /* ignore */ }

        const temp = localStorage.getItem('temperature');
        if (temp !== null && temp !== '') {
            const t = parseFloat(temp);
            if (!Number.isNaN(t)) opts.temperature = t;
        }

        const maxTokens = localStorage.getItem('maxTokens');
        if (maxTokens !== null && maxTokens !== '') {
            const n = parseInt(maxTokens, 10);
            // The backend caps this at 32768; skip nonsense rather than 422 the turn.
            if (Number.isInteger(n) && n > 0) opts.max_tokens = n;
        }

        // Checkboxes are stored as the strings "true"/"false".
        const includeMemory = localStorage.getItem('includeMemory');
        if (includeMemory !== null) opts.include_memory = includeMemory === 'true';

        const autoMemory = localStorage.getItem('autoMemory');
        if (autoMemory !== null) opts.auto_memory = autoMemory === 'true';

        return opts;
    }

    static async *streamMessage(conversationId, message, model = null, extra = {}) {
        const response = await fetch(`${API_BASE}/chat/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation_id: conversationId,
                message,
                model,
                ...API.getChatOptions(),
                ...extra,
            }),
        });

        if (!response.ok) {
            throw new Error(`API Error: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        // FIX 2: Always release the reader lock, even if an error is thrown mid-stream
        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            yield data;
                        } catch (e) {
                            console.error('Failed to parse SSE data', e);
                        }
                    }
                }
            }
        } finally {
            reader.releaseLock();
        }
    }

    // Bounded workspace runtime
    static async getWorkspaceComponents() {
        return (await this.request('/workspace/components')).json();
    }

    static async updateWorkspaceComponent(id, changes) {
        return (await this.request(`/workspace/components/${encodeURIComponent(id)}`, {
            method: 'PATCH', body: JSON.stringify(changes),
        })).json();
    }

    static async actOnWorkspaceComponent(id, action) {
        return (await this.request(`/workspace/components/${encodeURIComponent(id)}/actions`, {
            method: 'POST', body: JSON.stringify({ action }),
        })).json();
    }

    static async listWorkspaceTemplates() {
        return (await this.request('/workspace/templates')).json();
    }

    static async getWorkspaceTemplate(id) {
        return (await this.request(`/workspace/templates/${encodeURIComponent(id)}`)).json();
    }

    static async createWorkspaceTemplate(template) {
        return (await this.request('/workspace/templates', {
            method: 'POST', body: JSON.stringify(template),
        })).json();
    }

    static async addWorkspaceTemplateVersion(id, definition) {
        return (await this.request(`/workspace/templates/${encodeURIComponent(id)}/versions`, {
            method: 'POST', body: JSON.stringify({ definition }),
        })).json();
    }

    static async updateWorkspaceTemplate(id, status) {
        return (await this.request(`/workspace/templates/${encodeURIComponent(id)}`, {
            method: 'PATCH', body: JSON.stringify({ status }),
        })).json();
    }

    static async instantiateWorkspaceTemplate(id, data = {}, templateVersion = null) {
        return (await this.request(`/workspace/templates/${encodeURIComponent(id)}/instances`, {
            method: 'POST', body: JSON.stringify({ data, template_version: templateVersion }),
        })).json();
    }

    static async listWorkspaceExtensions() {
        return (await this.request('/workspace/extensions')).json();
    }

    static async installWorkspaceExtension(manifest, grantPermissions = []) {
        return (await this.request('/workspace/extensions', {
            method: 'POST', body: JSON.stringify({ manifest, grant_permissions: grantPermissions }),
        })).json();
    }

    static async actOnWorkspaceExtension(id, action, version = null) {
        return (await this.request(`/workspace/extensions/${encodeURIComponent(id)}/actions`, {
            method: 'POST', body: JSON.stringify({ action, ...(version === null ? {} : { version }) }),
        })).json();
    }

    static async actOnReminder(id, action) {
        return (await this.request(`/workspace/reminders/${encodeURIComponent(id)}/actions`, {
            method: 'POST', body: JSON.stringify({ action }),
        })).json();
    }

    static async createWorkflow(plan, idempotencyKey = crypto.randomUUID()) {
        return (await this.request('/workspace/workflows', {
            method: 'POST', body: JSON.stringify({ plan, idempotency_key: idempotencyKey }),
        })).json();
    }

    static async getWorkflows() {
        return (await this.request('/workspace/workflows')).json();
    }

    static async actOnWorkflow(id, action) {
        return (await this.request(`/workspace/workflows/${encodeURIComponent(id)}/actions`, {
            method: 'POST', body: JSON.stringify({ action }),
        })).json();
    }

    static async getWorkspaceNotifications() {
        return (await this.request('/workspace/notifications')).json();
    }

    static async ackWorkspaceNotification(id) {
        return (await this.request(`/workspace/notifications/${encodeURIComponent(id)}/ack`, { method: 'POST' })).json();
    }

    // Models
    static async getModels() {
        const response = await this.request('/ollama/models');
        return response.json();
    }

    static async switchModel(model) {
        const response = await this.request('/ollama/switch', {
            method: 'POST',
            body: JSON.stringify({ model }),
        });
        return response.json();
    }

    // Health
    static async getHealth() {
        const response = await this.request('/health');
        return response.json();
    }
}
