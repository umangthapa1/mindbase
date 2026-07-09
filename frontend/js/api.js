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
