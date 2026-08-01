# Frontend CSS

This directory contains Cascading Style Sheets for the frontend.

## Files

- `globals.css` - Defines CSS variables (design tokens) for colors, spacing, etc.

## Design Tokens

Colors and other design values are defined as CSS variables in `:root` in `globals.css`.
Use `var(--variable-name)` to reference these values in other CSS files or inline styles.

## Conventions

- Do not use Tailwind utility classes (they are not loaded).
- Style using CSS classes or inline styles.
- The intended palette is monochrome with white/light-grey accents.
