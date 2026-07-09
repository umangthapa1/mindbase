// ─── Markdown setup (run once, not on every render) ───────────────────────────
marked.setOptions({ breaks: true, gfm: true });

// Markdown rendering with code highlighting + XSS sanitization
function renderMarkdown(text) {
    const renderer = new marked.Renderer();

    renderer.code = (code) => {
        const highlighted = hljs.highlightAuto(code.text).value;
        return `<pre class="bg-slate-900 border border-slate-800 rounded p-3 overflow-x-auto"><code class="hljs">${highlighted}</code></pre>`;
    };

    renderer.codespan = (code) => {
        return `<code class="bg-slate-800 px-2 py-1 rounded text-sm font-mono">${code.text}</code>`;
    };

    renderer.link = (token) => {
        return `<a href="${token.href}" target="_blank" rel="noopener noreferrer" class="text-violet-400 hover:text-violet-300">${token.text}</a>`;
    };

    const rawHTML = marked.parse(text, { renderer });

    // FIX 1: Sanitize output to prevent XSS
    // Requires DOMPurify: <script src="https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.6/purify.min.js"></script>
    return typeof DOMPurify !== 'undefined'
        ? DOMPurify.sanitize(rawHTML, { ADD_ATTR: ['target'] })
        : rawHTML;
}

// Format timestamp
function formatTime(date) {
    const d = new Date(date);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Format date
function formatDate(date) {
    const d = new Date(date);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (d.toDateString() === today.toDateString()) {
        return 'Today';
    } else if (d.toDateString() === yesterday.toDateString()) {
        return 'Yesterday';
    } else {
        return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
}

// Truncate text
function truncate(text, length = 50) {
    return text.length > length ? text.substring(0, length) + '...' : text;
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Toasts live in js/toast.js (loaded before this file) so sub-pages can reuse them.

// DOM helpers — lightweight querySelector aliases (not jQuery)
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

function createElement(tag, className = '', textContent = '') {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (textContent) el.textContent = textContent;
    return el;
}
