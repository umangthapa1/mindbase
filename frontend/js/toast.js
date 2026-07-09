// Standalone, dependency-free toast notifications shared across all pages.
// type: 'info' | 'ok' | 'error'
function toast(message, type = 'info', duration = 3600) {
    let host = document.getElementById('toastHost');
    if (!host) {
        host = document.createElement('div');
        host.id = 'toastHost';
        host.className = 'toast-host';
        host.setAttribute('role', 'status');
        host.setAttribute('aria-live', 'polite');
        document.body.appendChild(host);
    }

    const el = document.createElement('div');
    el.className = `toast toast--${type}`;
    el.textContent = message;
    host.appendChild(el);

    const remove = () => {
        el.classList.add('leaving');
        el.addEventListener('animationend', () => el.remove(), { once: true });
        setTimeout(() => el.remove(), 300); // fallback if animationend doesn't fire
    };

    setTimeout(remove, duration);
    el.addEventListener('click', remove);
    return el;
}

// Promise-based confirmation modal — non-blocking replacement for window.confirm().
// Resolves true on confirm, false on cancel/escape/backdrop.
function confirmDialog(message, { confirmText = 'Delete', cancelText = 'Cancel', danger = true } = {}) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'confirm-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');

        const card = document.createElement('div');
        card.className = 'confirm-card';
        card.innerHTML = `
            <p class="confirm-msg"></p>
            <div class="confirm-actions">
                <button class="confirm-cancel" type="button"></button>
                <button class="confirm-ok ${danger ? 'is-danger' : ''}" type="button"></button>
            </div>`;
        card.querySelector('.confirm-msg').textContent = message;
        card.querySelector('.confirm-cancel').textContent = cancelText;
        card.querySelector('.confirm-ok').textContent = confirmText;
        overlay.appendChild(card);
        document.body.appendChild(overlay);

        const close = (result) => {
            overlay.classList.add('leaving');
            setTimeout(() => overlay.remove(), 180);
            document.removeEventListener('keydown', onKey);
            resolve(result);
        };
        const onKey = (e) => {
            if (e.key === 'Escape') close(false);
            if (e.key === 'Enter') close(true);
        };

        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });
        card.querySelector('.confirm-cancel').addEventListener('click', () => close(false));
        card.querySelector('.confirm-ok').addEventListener('click', () => close(true));
        document.addEventListener('keydown', onKey);

        requestAnimationFrame(() => card.querySelector('.confirm-ok').focus());
    });
}
