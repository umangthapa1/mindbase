# Mindbase Frontend - css/globals.css

## Overview
CSS file containing design tokens (CSS variables) and base styling for the Mindbase application. Defines the visual language including colors, spacing, typography, and component styles used throughout the interface.

## Responsibilities
- Define CSS custom properties (variables) for design tokens
- Establish base typography and spacing scales
- Provide reset/normalize-like base styles
- Define common component styles (buttons, inputs, cards, etc.)
- Set up color system with semantic meanings
- Define layout utilities and responsive breakpoints
- Create consistent visual language across all pages

## Design Tokens (CSS Variables)

### Color System
All colors defined as CSS variables on `:root` for easy theming:

```css
:root {
  /* Neutral palette */
  --bg-primary: #ffffff;
  --bg-secondary: #f8f9fa;
  --bg-tertiary: #f1f3f5;
  --bg-overlay: rgba(0, 0, 0, 0.5);
  
  --text-primary: #212529;
  --text-secondary: #6c757d;
  --text-tertiary: #868e96;
  --text-muted: #adb5bd;
  
  --border-color: #dee2e6;
  --border-color-hover: #adb5bd;
  
  /* Semantic colors */
  --success: #28a745;
  --info: #17a2b8;
  --warning: #ffc107;
  --danger: #dc3545;
  
  /* Interactive states */
  --primary: #007bff;        /* Main accent color */
  --primary-hover: #0069d9;
  --primary-active: #0062cc;
  
  /* Shadows */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.12);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
  --shadow-xl: 0 20px 25px rgba(0,0,0,0.15);
}
```

### Spacing Scale
Consistent spacing based on 4px grid:

```css
:root {
  /* Spacing */
  --space-0: 0rem;
  --space-1: 0.25rem;   /* 4px */
  --space-2: 0.5rem;    /* 8px */
  --space-3: 0.75rem;   /* 12px */
  --space-4: 1rem;      /* 16px */
  --space-5: 1.25rem;   /* 20px */
  --space-6: 1.5rem;    /* 24px */
  --space-8: 2rem;      /* 32px */
  --space-10: 2.5rem;   /* 40px */
  --space-12: 3rem;     /* 48px */
  --space-16: 4rem;     /* 64px */
  --space-20: 5rem;     /* 80px */
}
```

### Typography
Font sizes and weights:

```css
:root {
  /* Font sizes */
  --font-xs: 0.75rem;   /* 12px */
  --font-sm: 0.875rem;  /* 14px */
  --font-base: 1rem;    /* 16px */
  --font-lg: 1.125rem;  /* 18px */
  --font-xl: 1.25rem;   /* 20px */
  --font-2xl: 1.5rem;   /* 24px */
  --font-3xl: 1.875rem; /* 30px */
  --font-4xl: 2.25rem;  /* 36px */
  
  /* Font weights */
  --font-weight-light: 300;
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;
  
  /* Line heights */
  --line-height-tight: 1.2;
  --line-height-snug: 1.3;
  --line-height-normal: 1.5;
  --line-height-relaxed: 1.6;
  
  /* Letter spacing */
  --letter-spacing-tight: -0.025em;
  --letter-spacing-normal: 0;
  --letter-spacing-wide: 0.025em;
}
```

### Border Radius & Shadows
```css
:root {
  /* Border radius */
  --radius-none: 0;
  --radius-sm: 0.125rem;   /* 2px */
  --radius-md: 0.25rem;    /* 4px */
  --radius-lg: 0.5rem;     /* 8px */
  --radius-xl: 0.75rem;    /* 12px */
  --radius-full: 9999px;
  
  /* Transition */
  --transition-fast: 150ms ease-in-out;
  --transition-normal: 250ms ease-in-out;
  --transition-slow: 350ms ease-in-out;
}
```

## Base Styles

### Reset & Normalization
- Box-sizing: border-box applied universally
- Default font family: system UI fallback
- Text rendering optimizations
- Link styles reset
- Form element normalization

### Layout Containers
- `.container`: Max-width centered containers
- `.flex`: Flexbox utilities
- `.grid`: CSS grid utilities
- `.space-y-*`: Vertical spacing between children
- `.space-x-*`: Horizontal spacing between children

## Component Styles

### Buttons
```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-2) var(--space-4);
  font-size: var(--font-base);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-md);
  border: none;
  cursor: pointer;
  transition: var(--transition-normal);
  text-decoration: none;
}

.btn-primary {
  background: var(--primary);
  color: white;
}

.btn-primary:hover {
  background: var(--primary-hover);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-outline {
  background: transparent;
  color: var(--primary);
  border: 1px solid var(--primary);
}

.btn-outline:hover {
  background: var(--primary);
  color: white;
}

.btn-icon {
  width: 2.5rem;
  height: 2.5rem;
  padding: 0;
  border-radius: var(--radius-lg);
}
```

### Inputs & Form Elements
```css
.input, .textarea, .select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-base);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: var(--transition-normal);
}

.input:focus,
.textarea:focus,
.select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.25);
}

.input::placeholder,
.textarea::placeholder {
  color: var(--text-muted);
}
```

### Cards & Panels
```css
.card {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  box-shadow: var(--shadow-sm);
}

.card-header {
  border-bottom: 1px solid var(--border-color);
  padding-bottom: var(--space-2);
  margin-bottom: var(--space-3);
}

.card-body {
  padding: var(--space-3);
}

.card-footer {
  border-top: 1px solid var(--border-color);
  padding-top: var(--space-2);
  margin-top: var(--space-3);
}
```

### Navigation & Dock
```css
.dock {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
}

.dock-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition-normal);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: var(--font-xs);
}

.dock-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.dock-item-active {
  background: var(--primary);
  color: white;
}

.dock-item-icon {
  font-size: var(--font-lg);
  width: 1.75rem;
  height: 1.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
```

### Chat Interface
```css
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4);
  gap: var(--space-3);
}

.message {
  max-width: 80%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  word-wrap: break-word;
}

.user-message {
  background: var(--primary);
  color: white;
  margin-left: auto;
  border-bottom-right-radius: var(--radius-sm);
}

.assistant-message {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-bottom-left-radius: var(--radius-sm);
}

.system-message {
  background: var(--bg-tertiary);
  color: var(--text-muted);
  font-size: var(--font-sm);
  text-align: center;
  padding: var(--space-2);
}
```

### Toast Notifications
```css
.toast-container {
  position: fixed;
  top: var(--space-4);
  right: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  z-index: 1000;
}

.toast {
  min-width: 20rem;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  animation: slide-in 0.3s ease-out,
              fade-out 0.3s ease-in 2.7s forwards;
}

.toast-success {
  background: var(--success);
  color: white;
}

.toast-error {
  background: var(--danger);
  color: white;
}

.toast-warning {
  background: var(--warning);
  color: var(--text-primary);
}

.toast-info {
  background: var(--info);
  color: white;
}
```

### Responsive Breakpoints
```css
/* Mobile-first approach */
@media (min-width: 640px) {  /* sm */
  /* Adjustments for small screens */
}

@media (min-width: 768px) {  /* md */
  /* Tablet and up adjustments */
}

@media (min-width: 1024px) { /* lg */
  /* Desktop adjustments */
}

@media (min-width: 1280px) { /* xl */
  /* Large desktop adjustments */
}
```

## Utility Classes

### Display
```css
.flex { display: flex; }
.inline-flex { display: inline-flex; }
.grid { display: grid; }
.hidden { display: none; }
.visible { display: block; }
.invisible { visibility: hidden; }
```

### Text
```css
.text-left { text-align: left; }
.text-center { text-align: center; }
.text-right { text-align: right; }
.text-justify { text-align: justify; }

.text-xs { font-size: var(--font-xs); }
.text-sm { font-size: var(--font-sm); }
.text-base { font-size: var(--font-base); }
.text-lg { font-size: var(--font-lg); }
.text-xl { font-size: var(--font-xl); }
.text-2xl { font-size: var(--font-2xl); }

.font-light { font-weight: var(--font-weight-light); }
.font-normal { font-weight: var(--font-weight-normal); }
.font-medium { font-weight: var(--font-weight-medium); }
.font-semibold { font-weight: var(--font-weight-semibold); }
.font-bold { font-weight: var(--font-weight-bold); }

.italic { font-style: italic; }
.not-italic { font-style: normal; }

.uppercase { text-transform: uppercase; }
.lowercase { text-transform: lowercase; }
.capitalize { text-transform: capitalize; }

.leading-none { line-height: 1; }
.leading-tight { line-height: var(--line-height-tight); }
.leading-snug { line-height: var(--line-height-snug); }
.leading-normal { line-height: var(--line-height-normal); }
.leading-relaxed { line-height: var(--line-height-relaxed); }

.tracking-tight { letter-spacing: var(--letter-spacing-tight); }
.tracking-normal { letter-spacing: var(--letter-spacing-normal); }
.tracking-wide { letter-spacing: var(--letter-spacing-wide); }
```

### Spacing
```css
.m-0 { margin: var(--space-0); }
.m-1 { margin: var(--space-1); }
/* ... continues for all spacing values */
.mt-0 { margin-top: var(--space-0); }
.mb-0 { margin-bottom: var(--space-0); }
/* ... continues for all directions */

.p-0 { padding: var(--space-0); }
.p-1 { padding: var(--space-1); }
/* ... continues for all spacing values */
.pt-0 { padding-top: var(--space-0); }
.pb-0 { padding-bottom: var(--space-0); }
/* ... continues for all directions */
```

### Flex & Grid
```css
.flex-row { flex-direction: row; }
.flex-col { flex-direction: column; }
.flex-wrap { flex-wrap: wrap; }
.items-start { align-items: flex-start; }
.items-center { align-items: center; }
.items-end { align-items: flex-end; }
.justify-start { justify-content: flex-start; }
.justify-center { justify-content: center; }
.justify-end { justify-content: flex-end; }
.justify-between { justify-content: space-between; }
.justify-around { justify-content: space-around; }

.gap-0 { gap: var(--space-0); }
.gap-1 { gap: var(--space-1); }
/* ... continues for all spacing values */
```

### Visibility & Overflow
```css
.overflow-auto { overflow: auto; }
.overflow-hidden { overflow: hidden; }
.overflow-visible { overflow: visible; }
.overflow-scroll { overflow: scroll; }

.whitespace-normal { white-space: normal; }
.whitespace-nowrap { white-space: nowrap; }
.whitespace-pre { white-space: pre; }
.whitespace-pre-line { white-space: pre-line; }
.whitespace-pre-wrap { white-space: pre-wrap; }

.break-normal { overflow-wrap: normal; word-break: normal; }
.break-words { overflow-wrap: break-word; }
.break-all { word-break: break-all; }
```

### Transitions & Animations
```css
.transition-none { transition: none; }
.transition { transition: var(--transition-normal); }
.transition-colors { transition: color var(--transition-normal), background-color var(--transition-normal), border-color var(--transition-normal), opacity var(--transition-normal); }
.transition-opacity { transition: opacity var(--transition-normal); }
.transition-shadow { transition: box-shadow var(--transition-normal); }
```

### Interactive States
```css
.hover\:primary:hover { background-color: var(--primary); }
.hover\:secondary:hover { background-color: var(--bg-secondary); }
.hover\:text-white:hover { color: white; }
.focus\:outline-none:focus { outline: none; }
.focus\:ring-2:focus { box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.5); }
.disabled { pointer-events: none; opacity: 0.5; }
```

## Usage Guidelines

### Using Design Tokens
Always use CSS variables instead of hardcoded values:
```css
/* Good */
color: var(--text-primary);
background-color: var(--bg-secondary);
border-radius: var(--radius-md);

/* Avoid */
color: #212529;
background-color: #f8f9fa;
border-radius: 4px;
```

### Extending the System
When adding new colors or spacing values:
1. Add to the `:root` section in globals.css
2. Follow the naming convention
3. Ensure semantic meaning is clear
4. Update utility classes if needed

### Theme Considerations
The current design assumes:
- Light background with dark text
- Primary accent color for interactive elements
- Semantic colors for feedback (success, warning, error, info)
- Subtle shadows for depth
- Rounded corners for modern appearance

### Browser Support
- Uses modern CSS features (CSS variables, flexbox, grid)
- Fallbacks not provided for older browsers
- Targets modern evergreen browsers
- Mobile-responsive design

## Implementation Notes

### CSS Organization
- Variables defined at top for easy access
- Base styles reset/normalize common elements
- Component styles follow BEM-like naming
- Utility classes for rapid development
- Media queries for responsive behavior

### Performance
- Minimal use of !important
- Efficient selectors
- CSS variables reduce duplication
- Critical styles loaded in head

### Customization
To customize the theme:
1. Modify values in `:root` section
2. Maintain contrast ratios for accessibility
3. Update semantic colors if changing meaning
4. Consider dark mode extension (not currently implemented)

## Accessibility
- Color contrast ratios meet WCAG AA standards
- Focus styles visible for keyboard navigation
- Touch targets minimum 44x44px
- Respects user's reduced motion preferences
- Logical tab order in components