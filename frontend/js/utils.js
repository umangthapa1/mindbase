// ─── Markdown setup (run once, not on every render) ───────────────────────────
marked.setOptions({ breaks: true, gfm: true });

// Markdown rendering with code highlighting + XSS sanitization
function renderMarkdown(text) {
    const renderer = new marked.Renderer();

    renderer.code = (codeOrToken) => {
        // Marked v11 passes the source as a string; newer releases pass a token.
        const source = typeof codeOrToken === 'string' ? codeOrToken : codeOrToken.text;
        const highlighted = hljs.highlightAuto(source || '').value;
        return `<pre class="code-block"><button type="button" class="code-copy-btn" data-action="copy-code" aria-label="Copy code">Copy code</button><code class="hljs">${highlighted}</code></pre>`;
    };

    renderer.codespan = (codeOrToken) => {
        const source = typeof codeOrToken === 'string' ? codeOrToken : codeOrToken.text;
        return `<code class="inline-code">${escapeHTML(source || '')}</code>`;
    };

    renderer.link = (hrefOrToken, _title, text) => {
        // Marked v11 uses (href, title, text), while current releases pass a token.
        const href = typeof hrefOrToken === 'string' ? hrefOrToken : hrefOrToken.href;
        const label = typeof hrefOrToken === 'string' ? text : hrefOrToken.text;
        return `<a href="${escapeHTML(href || '')}" target="_blank" rel="noopener noreferrer" class="markdown-link">${escapeHTML(label || '')}</a>`;
    };

    // Chat and inbox content can contain literal addresses such as
    // `<noreply@example.com>`. Treat all raw HTML as text: it prevents Marked
    // from swallowing the rest of a message as an unknown HTML element and is
    // the safe default for model-generated content.
    renderer.html = (htmlOrToken) => {
        const source = typeof htmlOrToken === 'string' ? htmlOrToken : htmlOrToken.text;
        return escapeHTML(source || '');
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
