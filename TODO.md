# Accent Color System — Implementation Plan

1. ✅ Create `frontend/js/accent.js` (central accent system, presets, color utils, variants, persistence)
2. ✅ Add fallback accent vars + `[data-accent-active]` overrides to `frontend/css/globals.css` and `page-theme.css`
3. ✅ Add "Accent Color" UI card to `frontend/pages/settings.html`
4. ✅ Load `accent.js` in `<head>` after `theme.js` on all pages (index + 10 sub-pages + test pages)
5. ✅ Verify: presets, custom color, persistence, theme+accent independence, reset, contrast

## Verification results
- `accent.js` boots cleanly, exposes `window.MindbaseAccent`
- 10 presets defined; custom swatch opens a hidden native `<input type="color">` picker (native input element removed from markup per user request)
- Color variants derived correctly (accent, hover=darker, light, soft, border, ring, glow, text)
- Contrast: dark accent → white text, light accent → dark text
- Invalid hex rejected (state stays default); 3-digit hex normalized
- Custom `#FF00FF` → applied + persisted; reset restores default
- Persistence via `localStorage['mindbase-accent']` + `['mindbase-accent-custom']`
- `[data-accent-active]` gates accent-colored primary buttons so default appearance is unchanged
- accent.js loaded on index + all 10 sub-pages + test_typing.html
