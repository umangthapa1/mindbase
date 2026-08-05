const THEME_STORAGE_KEY = 'theme';
const DEFAULT_THEME = 'dark';
const SUPPORTED_THEMES = new Set(['dark', 'light', 'black-gold', 'blue-night', 'grey-ash', 'hellish-red']);

function normalizeTheme(theme) {
    return SUPPORTED_THEMES.has(theme) ? theme : DEFAULT_THEME;
}

function applyTheme(theme) {
    const normalized = normalizeTheme(theme);
    document.documentElement.dataset.theme = normalized;
    return normalized;
}

function emitThemeChange(theme) {
    window.dispatchEvent(new CustomEvent('mindbase-themechange', {
        detail: { theme },
    }));
}

function getStoredTheme() {
    try {
        return normalizeTheme(localStorage.getItem(THEME_STORAGE_KEY));
    } catch {
        return DEFAULT_THEME;
    }
}

function setStoredTheme(theme) {
    const normalized = normalizeTheme(theme);

    try {
        localStorage.setItem(THEME_STORAGE_KEY, normalized);
    } catch {}

    applyTheme(normalized);
    emitThemeChange(normalized);
    return normalized;
}

function bootstrapTheme() {
    applyTheme(getStoredTheme());

    window.addEventListener('storage', (event) => {
        if (event.key === THEME_STORAGE_KEY) {
            const normalized = normalizeTheme(event.newValue);
            applyTheme(normalized);
            emitThemeChange(normalized);
        }
    });
}

window.MindbaseTheme = {
    applyTheme,
    bootstrapTheme,
    getStoredTheme,
    setStoredTheme,
};

bootstrapTheme();