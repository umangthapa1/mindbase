const THEME_STORAGE_KEY = 'theme';
const DEFAULT_THEME = 'dark';
const SUPPORTED_THEMES = new Set(['system', 'dark', 'light', 'black-gold', 'blue-night', 'grey-ash', 'hellish-red']);

function normalizeTheme(theme) {
    return SUPPORTED_THEMES.has(theme) ? theme : DEFAULT_THEME;
}

function resolveSystemTheme() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyTheme(theme) {
    const normalized = normalizeTheme(theme);
    const resolved = normalized === 'system' ? resolveSystemTheme() : normalized;
    document.documentElement.dataset.theme = resolved;
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

    try {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
            if (getStoredTheme() === 'system') {
                applyTheme('system');
                emitThemeChange('system');
            }
        });
    } catch (e) {
        console.error(e);
    }
}

window.MindbaseTheme = {
    applyTheme,
    bootstrapTheme,
    getStoredTheme,
    setStoredTheme,
};

bootstrapTheme();