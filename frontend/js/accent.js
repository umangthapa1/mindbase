/* ── accent.js ─────────────────────────────────────────────
   Mindbase global accent color system.

   A lightweight, dependency-free accent layer that sits on top
   of the existing theme system. Themes keep full control of the
   environment (background, surface, borders, text, etc.) while
   this module overrides ONLY the accent-related CSS variables.

   The accent is applied as inline CSS custom properties on the
   <html> element, so it:
     • works across every theme
     • persists across reloads
     • updates the UI instantly (no reload or Save button)
     • falls back to the active theme's default accent when the
       user has not chosen a custom accent (no visual change)

   Exposed as window.MindbaseAccent.
─────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  if (window.MindbaseAccent) return;

  /* ── Storage keys ── */
  const ACCENT_KEY = 'mindbase-accent';          // active accent (hex) or '' for default
  const CUSTOM_KEY = 'mindbase-accent-custom';   // last custom color so it can be preserved

  /* ── Preset accents (centralized) ── */
  const accentPresets = [
    { name: 'Blue',     color: '#3B82F6' },
    { name: 'Purple',   color: '#8B5CF6' },
    { name: 'Violet',   color: '#7C3AED' },
    { name: 'Cyan',     color: '#06B6D4' },
    { name: 'Green',    color: '#22C55E' },
    { name: 'Emerald',  color: '#10B981' },
    { name: 'Orange',   color: '#F97316' },
    { name: 'Red',      color: '#EF4444' },
    { name: 'Pink',     color: '#EC4899' },
    { name: 'Yellow',   color: '#EAB308' },
  ];

  /* ── Default accent per theme (used when no custom accent is active) ──
     These mirror the --accent values already defined in globals.css so
     that existing users see no change until they pick an accent. */
  const themeDefaultAccents = {
    'dark':         '#ffffff',
    'light':        '#111827',
    'black-gold':   '#d0a34b',
    'blue-night':   '#8fb0ff',
    'grey-ash':     '#6b7280',
    'hellish-red':  '#ff6b6b',
  };

  const clamp = (n) => Math.max(0, Math.min(255, Math.round(n)));

  /* ── Color utilities ── */
  function normalizeHex(input) {
    if (typeof input !== 'string') return null;
    let hex = input.trim().replace(/^#/, '');
    if (/^[0-9a-fA-F]{3}$/.test(hex)) {
      hex = hex.split('').map((c) => c + c).join('');
    }
    if (!/^[0-9a-fA-F]{6}$/.test(hex)) return null;
    return '#' + hex.toLowerCase();
  }

  function hexToRgb(hex) {
    const h = normalizeHex(hex);
    if (!h) return null;
    return {
      r: parseInt(h.slice(1, 3), 16),
      g: parseInt(h.slice(3, 5), 16),
      b: parseInt(h.slice(5, 7), 16),
    };
  }

  function rgbToHex({ r, g, b }) {
    return '#' + [r, g, b].map((n) => clamp(n).toString(16).padStart(2, '0')).join('');
  }

  /** Mix a hex color toward black (amount 0..1) or toward white (amount < 0). */
  function shade(hex, amount) {
    const { r, g, b } = hexToRgb(hex) || { r: 255, g: 255, b: 255 };
    const t = amount >= 0 ? 0 : 255; // target: black when darkening, white when lightening
    const k = Math.min(1, Math.abs(amount));
    return rgbToHex({
      r: r + (t - r) * k,
      g: g + (t - g) * k,
      b: b + (t - b) * k,
    });
  }

  function rgba(hex, alpha) {
    const { r, g, b } = hexToRgb(hex) || { r: 255, g: 255, b: 255 };
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  /** Relative luminance per WCAG: 0 (black) → 1 (white). */
  function luminance(hex) {
    const { r, g, b } = hexToRgb(hex) || { r: 255, g: 255, b: 255 };
    const lin = (c) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  }

  /** Return black or white text depending on background contrast. */
  function contrastText(hex) {
    const l = luminance(hex);
    // If the background is light, use dark text; otherwise white.
    return l > 0.5 ? '#111317' : '#ffffff';
  }

  /* ── Variant computation ── */
  function computeAccentVars(color) {
    const base = normalizeHex(color) || '#6366f1';
    return {
      '--accent': base,
      '--accent-hover': shade(base, 0.18),
      '--accent-light': rgba(base, 0.15),
      '--accent-soft': rgba(base, 0.10),
      '--accent-border': rgba(base, 0.35),
      '--accent-ring': rgba(base, 0.25),
      '--accent-glow': rgba(base, 0.25),
      '--accent-text': contrastText(base),
    };
  }

  /* ── State ── */
  let activeAccent = '';   // '' = use theme default

  function getActiveTheme() {
    return document.documentElement.dataset.theme || 'dark';
  }

  function getThemeDefaultAccent() {
    return themeDefaultAccents[getActiveTheme()] || '#ffffff';
  }

  function getCurrentAccent() {
    return activeAccent || getThemeDefaultAccent();
  }

  /* ── Application ── */
  function applyAccent(color) {
    const base = color ? normalizeHex(color) : null;
    const source = base || getThemeDefaultAccent();
    const vars = computeAccentVars(source);
    const root = document.documentElement;

    // Remove accent-specific inline vars first, then re-apply.
    Object.keys(vars).forEach((k) => root.style.removeProperty(k));
    Object.keys(vars).forEach((k) => root.style.setProperty(k, vars[k]));

    // Flag so CSS can apply accent-styled primaries only when user chose one.
    if (base) root.setAttribute('data-accent-active', '');
    else root.removeAttribute('data-accent-active');

    return source;
  }

  /* ── Persistence ── */
  function getStoredAccent() {
    try {
      const v = localStorage.getItem(ACCENT_KEY);
      return v === null ? '' : normalizeHex(v) || '';
    } catch {
      return '';
    }
  }

  function getStoredCustom() {
    try {
      return normalizeHex(localStorage.getItem(CUSTOM_KEY)) || '';
    } catch {
      return '';
    }
  }

  function setStoredAccent(color) {
    const normalized = color ? normalizeHex(color) : '';
    try {
      if (normalized) localStorage.setItem(ACCENT_KEY, normalized);
      else localStorage.removeItem(ACCENT_KEY);
    } catch {}
  }

  function setStoredCustom(color) {
    const normalized = color ? normalizeHex(color) : '';
    try {
      if (normalized) localStorage.setItem(CUSTOM_KEY, normalized);
      else localStorage.removeItem(CUSTOM_KEY);
    } catch {}
  }

  /* ── Public API ── */
  function setAccent(color) {
    const normalized = color ? normalizeHex(color) : '';
    if (color && !normalized) return false; // invalid → ignore
    activeAccent = normalized;
    setStoredAccent(normalized);
    applyAccent(normalized);
    emit(normalized);
    return true;
  }

  function setCustomAccent(color) {
    const normalized = normalizeHex(color);
    if (!normalized) return false;
    setStoredCustom(normalized);
    return setAccent(normalized);
  }

  function resetAccent() {
    activeAccent = '';
    setStoredAccent('');
    applyAccent('');
    emit('');
    return true;
  }

  function emit(accent) {
    window.dispatchEvent(new CustomEvent('mindbase-accentchange', {
      detail: { accent: accent || getThemeDefaultAccent(), isDefault: !accent },
    }));
  }

  function getStoredAccentState() {
    return activeAccent;
  }

  function isDefault() {
    return !activeAccent;
  }

  /* ── Bootstrap ── */
  function bootstrap() {
    activeAccent = getStoredAccent();
    applyAccent(activeAccent);

    // Cross-tab sync
    window.addEventListener('storage', (event) => {
      if (event.key === ACCENT_KEY) {
        activeAccent = normalizeHex(event.newValue) || '';
        applyAccent(activeAccent);
        emit(activeAccent);
      }
    });

    // If the theme changes (e.g. another tab), re-derive default accent.
    window.addEventListener('mindbase-themechange', () => {
      if (!activeAccent) applyAccent('');
    });
  }

  window.MindbaseAccent = {
    accentPresets,
    themeDefaultAccents,
    normalizeHex,
    computeAccentVars,
    getCurrentAccent,
    getStoredAccent,
    getStoredCustom,
    setAccent,
    setCustomAccent,
    resetAccent,
    getStoredAccentState: getStoredAccentState,
    isDefault,
    bootstrap,
  };

  bootstrap();
})();
