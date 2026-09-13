# `frontend/js/theme.js`

Theme and background-pattern persistence exposed as `window.MindbaseTheme`.

## Supported themes

`system`, `dark`, `light`, `black-gold`, `blue-night`, `grey-ash`, and `hellish-red`.

`system` resolves to the operating system preference through `prefers-color-scheme`.

## Supported patterns

`none`, `grid`, `dots`, and `cross`. Values are stored in `localStorage` and applied as `data-theme` and `data-pattern` attributes on `<html>`.

## Public API

The module exposes `applyTheme()`, `bootstrapTheme()`, `getStoredTheme()`, `setStoredTheme()`, `applyPattern()`, `getStoredPattern()`, and `setStoredPattern()`.

Theme changes emit `mindbase-themechange`; storage events synchronize theme and pattern changes across open tabs.
