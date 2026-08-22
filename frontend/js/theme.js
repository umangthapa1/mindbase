const THEME_STORAGE_KEY = 'theme';
const DEFAULT_THEME = 'dark';
const SUPPORTED_THEMES = new Set(['system', 'dark', 'light', 'black-gold', 'blue-night', 'grey-ash', 'hellish-red']);

const PATTERN_STORAGE_KEY = 'pattern';
const DEFAULT_PATTERN = 'none';
const SUPPORTED_PATTERNS = new Set(['none', 'grid', 'dots', 'cross']);

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

function normalizePattern(pattern) {
    return SUPPORTED_PATTERNS.has(pattern) ? pattern : DEFAULT_PATTERN;
}

function applyPattern(pattern) {
    const normalized = normalizePattern(pattern);
    document.documentElement.dataset.pattern = normalized;
    return normalized;
}

function getStoredPattern() {
    try {
        return normalizePattern(localStorage.getItem(PATTERN_STORAGE_KEY));
    } catch {
        return DEFAULT_PATTERN;
    }
}

function setStoredPattern(pattern) {
    const normalized = normalizePattern(pattern);
    try {
        localStorage.setItem(PATTERN_STORAGE_KEY, normalized);
    } catch {}
    applyPattern(normalized);
    return normalized;
}

function bootstrapTheme() {
    applyTheme(getStoredTheme());
    applyPattern(getStoredPattern());

    window.addEventListener('storage', (event) => {
        if (event.key === THEME_STORAGE_KEY) {
            const normalized = normalizeTheme(event.newValue);
            applyTheme(normalized);
            emitThemeChange(normalized);
        } else if (event.key === PATTERN_STORAGE_KEY) {
            const normalized = normalizePattern(event.newValue);
            applyPattern(normalized);
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
    applyPattern,
    getStoredPattern,
    setStoredPattern,
};

bootstrapTheme();