/* ── dock.js ──────────────────────────────────────────────
   Shared navigation dock injected into every sub-page.
   Mirrors the dock on the chat page (index.html) so the whole
   app shares one persistent, mobile-aware navigation rail.

   Load on sub-pages only — it self-skips if a dock already
   exists (e.g. the chat page, which ships its own markup).
─────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  if (document.querySelector('.dock')) return; // chat page already has one

  // Brand mark (matches index.html)
  const LOGO = `
    <svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect x="2"  y="2"  width="7" height="7" rx="2" fill="rgba(255,255,255,0.70)"/>
      <rect x="11" y="2"  width="7" height="7" rx="2" fill="rgba(255,255,255,0.35)"/>
      <rect x="2"  y="11" width="7" height="7" rx="2" fill="rgba(255,255,255,0.35)"/>
      <rect x="11" y="11" width="7" height="7" rx="2" fill="rgba(255,255,255,0.18)"/>
    </svg>`;

  // [page key, label, href, inner SVG] — order matches the chat dock
  const ITEMS = [
    ['chat', 'Chat', '/',
      `<path d="M2.5 3.5h15a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H5.5l-3 3V4.5a1 1 0 0 1 1-1z"/>`],
    ['memory', 'Memory', '/pages/memory.html',
      `<ellipse cx="10" cy="6" rx="7" ry="3"/><path d="M3 6v4c0 1.66 3.13 3 7 3s7-1.34 7-3V6"/><path d="M3 10v4c0 1.66 3.13 3 7 3s7-1.34 7-3v-4"/>`],
    ['documents', 'Documents', '/pages/documents.html',
      `<path d="M11.5 2.5H5.5a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V6.5L11.5 2.5z"/><polyline points="11.5 2.5 11.5 6.5 15.5 6.5"/><line x1="7" y1="9.5" x2="13" y2="9.5"/><line x1="7" y1="12.5" x2="11" y2="12.5"/>`],
    ['email', 'Email', '/pages/email.html',
      `<rect x="2.5" y="4" width="15" height="12" rx="1.5"/><path d="M3 5.5l6.3 5a1.2 1.2 0 0 0 1.4 0L17 5.5"/>`],
    ['notes', 'Notes', '/pages/notes.html',
      `<path d="M13.5 2.5h-8a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1v-9.5l-4-4.5z"/><line x1="7" y1="8" x2="13" y2="8"/><line x1="7" y1="11" x2="13" y2="11"/><line x1="7" y1="14" x2="10" y2="14"/>`],
    ['calendar', 'Calendar', '/pages/calendar.html',
      `<rect x="2.5" y="3.5" width="15" height="14" rx="1.5"/><line x1="6.5" y1="2" x2="6.5" y2="5"/><line x1="13.5" y1="2" x2="13.5" y2="5"/><line x1="2.5" y1="8" x2="17.5" y2="8"/>`],
    ['tasks', 'Tasks', '/pages/tasks.html',
      `<path d="M8.5 5.5h8M8.5 10h8M8.5 14.5h5"/><polyline points="4 5 5.5 6.5 8 4"/><polyline points="4 9.5 5.5 11 8 8.5"/><line x1="4" y1="14.5" x2="6.5" y2="14.5"/>`],
    ['research', 'Research', '/pages/research.html',
      `<circle cx="8.5" cy="8.5" r="5"/><line x1="12.5" y1="12.5" x2="17" y2="17"/>`],
    ['dashboard', 'Dashboard', '/pages/dashboard.html',
      `<rect x="3" y="4" width="14" height="13" rx="2"/><line x1="7" y1="9" x2="13" y2="9"/><line x1="7" y1="12.5" x2="10" y2="12.5"/>`],
    ['agents', 'Agents', '/pages/agents.html',
      `<polygon points="10 2 13.5 8 18 9 14 13 15 18 10 15.5 5 18 6 13 2 9 6.5 8"/>`],
  ];

  const SETTINGS = ['settings', 'Settings', '/pages/settings.html',
    `<circle cx="10" cy="10" r="2.5"/><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.22 4.22l1.42 1.42M14.36 14.36l1.42 1.42M4.22 15.78l1.42-1.42M14.36 5.64l1.42-1.42"/>`];

  // Which item is current, derived from the URL
  let activeKey = 'chat';
  const match = location.pathname.match(/\/pages\/([a-z-]+)\.html/i);
  if (match) activeKey = match[1].toLowerCase();

  const navIcon = (inner) =>
    `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;

  const linkFor = ([key, label, href, inner]) => {
    const isActive = key === activeKey;
    return `<a href="${href}" class="dock-item${isActive ? ' active' : ''}" data-page="${key}"
              aria-label="${label}"${isActive ? ' aria-current="page"' : ''}>
              ${navIcon(inner)}<span class="tooltip">${label}</span>
            </a>`;
  };

  const dock = document.createElement('nav');
  dock.className = 'dock dock--fixed';
  dock.setAttribute('role', 'navigation');
  dock.setAttribute('aria-label', 'Main navigation');
  dock.innerHTML = `
    <a class="dock-logo" href="/" aria-label="Mindbase home">${LOGO}</a>
    <div class="dock-nav">${ITEMS.map(linkFor).join('')}</div>
    <div class="dock-bottom">
      <div class="dock-divider"></div>
      ${linkFor(SETTINGS)}
    </div>`;

  document.body.classList.add('has-app-dock');
  document.body.insertBefore(dock, document.body.firstChild);
})();
