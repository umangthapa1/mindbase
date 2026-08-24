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
