/* ──────────────────────────────────────────────────────────
   Mindbase · Email inbox
   Handles Gmail connection status, syncing, listing, reading
   and summarizing messages via the /api/email/* endpoints.
   ────────────────────────────────────────────────────────── */

(() => {
  const API_BASE = "/api/email";

  const els = {
    connectionCard: document.getElementById("connectionCard"),
    syncBtn: document.getElementById("syncBtn"),
    lastSynced: document.getElementById("lastSynced"),
    emailList: document.getElementById("emailList"),
    emailDetail: document.getElementById("emailDetail"),
    emailDetailEmpty: document.getElementById("emailDetailEmpty"),
    headerUnreadCount: document.getElementById("headerUnreadCount"),
    sidebarUnreadCount: document.getElementById("sidebarUnreadCount"),
    mailboxItems: document.querySelectorAll(".mailbox-item"),
  };

  let state = {
    connected: false,
    filter: "all", // "all" | "unread"
    emails: [],
    selectedId: null,
  };

  // ── Helpers ─────────────────────────────────────────────
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str ?? "";
    return div.innerHTML;
  }

  function formatTime(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";

    const now = new Date();
    const sameDay = date.toDateString() === now.toDateString();
    if (sameDay) {
      return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    }

    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) return "Yesterday";

    const sameYear = date.getFullYear() === now.getFullYear();
    return date.toLocaleDateString([], sameYear
      ? { month: "short", day: "numeric" }
      : { month: "short", day: "numeric", year: "numeric" });
  }

  function formatFullDate(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString([], {
      month: "short", day: "numeric", year: "numeric",
      hour: "numeric", minute: "2-digit",
    });
  }

  function senderName(raw) {
    if (!raw) return "(unknown sender)";
    // "Jane Doe <jane@example.com>" → "Jane Doe"
    const match = raw.match(/^"?([^"<]*)"?\s*(<.*>)?$/);
    const name = (match && match[1].trim()) || raw;
    return name || raw;
  }

  function setUnreadBadges(count) {
    [els.headerUnreadCount, els.sidebarUnreadCount].forEach((el) => {
      if (!el) return;
      el.textContent = String(count);
      el.dataset.count = String(count);
    });
  }

  // ── Connection status ──────────────────────────────────
  async function checkConnection() {
    try {
      const res = await fetch(`${API_BASE}/status`);
      const data = await res.json();
      state.connected = !!data.connected;
    } catch (err) {
      console.error("Failed to check Gmail status:", err);
      state.connected = false;
    }
    renderConnectionCard();
    return state.connected;
  }

  function renderConnectionCard() {
    if (state.connected) {
      els.connectionCard.innerHTML = `
        <span class="connection-dot"></span>Gmail connected
        <button class="pill-btn secondary" id="disconnectBtn">Disconnect</button>
      `;
      document.getElementById("disconnectBtn")?.addEventListener("click", disconnectGmail);
    } else {
      els.connectionCard.innerHTML = `
        Connect your Gmail account to read your inbox here.
        <button class="pill-btn" id="connectBtn">Connect Gmail</button>
      `;
      document.getElementById("connectBtn")?.addEventListener("click", connectGmail);
    }
  }

  async function connectGmail() {
    try {
      const res = await fetch(`${API_BASE}/auth-url`);
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (err) {
      console.error("Failed to get Gmail auth URL:", err);
      (typeof toast === 'function' ? toast("Couldn't start Gmail connection. Is the server running?", 'error') : null);
    }
  }

  async function disconnectGmail() {
    try {
      await fetch(`${API_BASE}/disconnect`, { method: "POST" });
      state.connected = false;
      state.emails = [];
      renderConnectionCard();
      renderEmailList();
      renderEmptyDetail();
      setUnreadBadges(0);
    } catch (err) {
      console.error("Failed to disconnect Gmail:", err);
    }
  }

  // ── Sync ────────────────────────────────────────────────
  async function syncInbox() {
    if (!state.connected) {
      connectGmail();
      return;
    }

    els.syncBtn.classList.add("is-syncing");
    els.syncBtn.disabled = true;

    try {
      const res = await fetch(`${API_BASE}/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_results: 25, query: "in:inbox" }),
      });

      if (!res.ok) throw new Error(`Sync failed: ${res.status}`);

      const data = await res.json();
      els.lastSynced.textContent = data.new_count > 0
        ? `Synced · ${data.new_count} new`
        : "Synced · up to date";

      await loadInbox();
    } catch (err) {
      console.error("Inbox sync failed:", err);
      els.lastSynced.textContent = "Sync failed";
    } finally {
      els.syncBtn.classList.remove("is-syncing");
      els.syncBtn.disabled = false;
    }
  }

  // ── Inbox list ──────────────────────────────────────────
  async function loadInbox() {
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (state.filter === "unread") params.set("unread_only", "true");

      const res = await fetch(`${API_BASE}/inbox?${params.toString()}`);
      if (!res.ok) throw new Error(`Inbox load failed: ${res.status}`);

      const data = await res.json();
      state.emails = data.emails || [];

      const unreadCount = state.filter === "unread"
        ? state.emails.length
        : state.emails.filter((e) => e.is_unread).length;
      setUnreadBadges(unreadCount);

      renderEmailList();
    } catch (err) {
      console.error("Failed to load inbox:", err);
      els.emailList.innerHTML = `
        <div class="empty-state">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="10" cy="10" r="7"/><line x1="10" y1="6" x2="10" y2="10.5"/><line x1="10" y1="13.5" x2="10" y2="13.6"/>
          </svg>
          <h3>Couldn't load your inbox</h3>
          <p>Check that the Mindbase server is running and try syncing again.</p>
        </div>
      `;
    }
  }

  function renderEmailList() {
    if (!state.connected) {
      els.emailList.innerHTML = `
        <div class="empty-state">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="2.5" y="4" width="15" height="12" rx="1.5"/>
            <path d="M3 5.5l6.3 5a1.2 1.2 0 0 0 1.4 0L17 5.5"/>
          </svg>
          <h3>No inbox connected yet</h3>
          <p>Connect your Gmail account to start reading and summarizing your emails here.</p>
          <button class="pill-btn" id="emptyConnectBtn">Connect Gmail</button>
        </div>
      `;
      document.getElementById("emptyConnectBtn")?.addEventListener("click", connectGmail);
      return;
    }

    if (state.emails.length === 0) {
      const msg = state.filter === "unread"
        ? "You're all caught up — no unread emails."
        : "No emails yet. Try syncing your inbox.";
      els.emailList.innerHTML = `
        <div class="empty-state">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M5 10l3.5 3.5L15 7"/>
          </svg>
          <h3>${state.filter === "unread" ? "All caught up" : "Nothing here yet"}</h3>
          <p>${escapeHtml(msg)}</p>
          <button class="pill-btn" id="emptySyncBtn">Sync inbox</button>
        </div>
      `;
      document.getElementById("emptySyncBtn")?.addEventListener("click", syncInbox);
      return;
    }

    els.emailList.innerHTML = state.emails.map((email) => `
      <div class="email-row ${email.is_unread ? "is-unread" : ""} ${email.id === state.selectedId ? "is-selected" : ""}"
           data-id="${escapeHtml(email.id)}">
        <div class="email-row-top">
          <span class="email-sender">${escapeHtml(senderName(email.sender))}</span>
          <span class="email-time">${escapeHtml(formatTime(email.received_at))}</span>
        </div>
        <span class="email-subject">${escapeHtml(email.subject || "(no subject)")}</span>
        <span class="email-snippet">${escapeHtml(email.snippet || "")}</span>
      </div>
    `).join("");

    els.emailList.querySelectorAll(".email-row").forEach((row) => {
      row.addEventListener("click", () => openEmail(row.dataset.id));
    });
  }

  // ── Detail pane ─────────────────────────────────────────
  function renderEmptyDetail() {
    els.emailDetail.innerHTML = `
      <div class="email-detail-empty">
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="2.5" y="4" width="15" height="12" rx="1.5"/>
          <path d="M3 5.5l6.3 5a1.2 1.2 0 0 0 1.4 0L17 5.5"/>
        </svg>
        <p>Select an email to read it</p>
      </div>
    `;
    els.emailDetail.classList.remove("is-active");
    els.emailList.classList.remove("is-hidden");
  }

  async function openEmail(id) {
    state.selectedId = id;
    renderEmailList();

    els.emailDetail.classList.add("is-active");
    els.emailList.classList.add("is-hidden");

    els.emailDetail.innerHTML = `<div class="email-detail-empty"><p>Loading…</p></div>`;

    try {
      const res = await fetch(`${API_BASE}/${encodeURIComponent(id)}`);
      if (!res.ok) throw new Error(`Failed to load email: ${res.status}`);
      const email = await res.json();
      renderEmailDetail(email);

      // Reflect read state locally (server-side syncs will reconcile too)
      const local = state.emails.find((e) => e.id === id);
      if (local && local.is_unread) {
        local.is_unread = false;
        const unreadCount = state.emails.filter((e) => e.is_unread).length;
        setUnreadBadges(state.filter === "unread" ? state.emails.length - 1 : unreadCount);
        renderEmailList();
      }
    } catch (err) {
      console.error("Failed to open email:", err);
      els.emailDetail.innerHTML = `
        <div class="email-detail-empty">
          <p>Couldn't load this email. Try again.</p>
        </div>
      `;
    }
  }

  function renderEmailDetail(email) {
    els.emailDetail.innerHTML = `
      <button class="email-detail-back" id="backBtn">
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="12 4 6 10 12 16"/>
        </svg>
        Back to inbox
      </button>

      <div class="email-detail-header">
        <h2 class="email-detail-subject">${escapeHtml(email.subject || "(no subject)")}</h2>
        <div class="email-detail-meta">
          <div class="email-detail-from">
            ${escapeHtml(senderName(email.sender))}
            <span>${escapeHtml(email.sender || "")}</span>
          </div>
          <div class="email-detail-date">${escapeHtml(formatFullDate(email.received_at))}</div>
        </div>
      </div>

      <button class="pill-btn secondary" id="summarizeBtn" style="align-self:flex-start; margin-bottom:18px;">
        Summarize
      </button>

      <div class="email-detail-body">${escapeHtml(email.body || email.snippet || "(no content)")}</div>

      <div class="email-summary" id="summaryBox" style="display:none;"></div>
    `;

    document.getElementById("backBtn")?.addEventListener("click", renderEmptyDetail);
    document.getElementById("summarizeBtn")?.addEventListener("click", () => summarizeEmail(email.id));
  }

  async function summarizeEmail(id) {
    const btn = document.getElementById("summarizeBtn");
    const box = document.getElementById("summaryBox");
    if (!btn || !box) return;

    btn.disabled = true;
    btn.textContent = "Summarizing…";

    try {
      const res = await fetch(`${API_BASE}/${encodeURIComponent(id)}/summarize`, { method: "POST" });
      if (!res.ok) throw new Error(`Summarize failed: ${res.status}`);
      const data = await res.json();

      box.style.display = "block";
      box.innerHTML = `<span class="email-summary-label">Summary</span>${escapeHtml(data.summary || "")}`;
    } catch (err) {
      console.error("Failed to summarize email:", err);
      box.style.display = "block";
      box.innerHTML = `<span class="email-summary-label">Summary</span>Couldn't generate a summary right now.`;
    } finally {
      btn.disabled = false;
      btn.textContent = "Summarize";
    }
  }

  // ── Filters ─────────────────────────────────────────────
  els.mailboxItems.forEach((item) => {
    item.addEventListener("click", () => {
      els.mailboxItems.forEach((i) => i.classList.remove("is-active"));
      item.classList.add("is-active");
      state.filter = item.dataset.filter;
      state.selectedId = null;
      renderEmptyDetail();
      loadInbox();
    });
  });

  // ── Wire up ─────────────────────────────────────────────
  els.syncBtn.addEventListener("click", syncInbox);

  // ── Init ────────────────────────────────────────────────
  (async function init() {
    const connected = await checkConnection();
    if (connected) {
      await loadInbox();
    } else {
      renderEmailList();
    }
  })();
})();