# `frontend/js/accent.js`

Global accent-color system exposed as `window.MindbaseAccent`.

## Behavior

- Applies an accent on top of the active theme through CSS custom properties.
- Persists the active accent in `localStorage` under `mindbase-accent`.
- Preserves the last custom color under `mindbase-accent-custom`.
- Supports ten curated presets and arbitrary six-digit hex colors.
- Derives hover, soft, border, ring, glow, and readable text variants.
- Uses WCAG relative luminance to choose black or white accent text.
- Synchronizes accent changes across tabs with the `storage` event.
- Re-derives the theme default when the theme changes and no custom accent is active.

## Public API

`accentPresets`, `themeDefaultAccents`, `normalizeHex()`, `setAccent()`, `setCustomAccent()`, `resetAccent()`, `getStoredAccentState()`, and `isDefault()` are exposed on `window.MindbaseAccent`.
