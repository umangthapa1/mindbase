# Mindbase Frontend - css/page-theme.css

## Overview
Shared CSS file containing common styling for all application pages. Provides consistent chrome (headers, footers, layout containers) and page-level styling that ensures visual consistency across different views in the Mindbase application.

## Responsibilities
- Define shared layout structures for pages
- Style page headers and footers consistently
- Provide consistent container styling for page content
- Define common page-specific components
- Establish vertical rhythm and spacing for pages
- Style shared elements like breadcrumbs, tags, badges
- Provide dark/light mode considerations (though primarily light mode)
- Ensure consistent typography treatment across pages

## Page Layout Structure

### Basic Page Structure
All pages in Mindbase follow this basic structure when using page-theme.css:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <!-- Page-specific title -->
    <link rel="stylesheet" href="../css/globals.css?v=...">
    <link rel="stylesheet" href="../css/page-theme.css?v=...">
</head>
<body>
    <div class="page-container">
        <!-- Page Header -->
        <header class="page-header">
            <!-- Page title, actions, breadcrumbs -->
        </header>
        
        <!-- Page Content -->
        <main class="page-content">
            <!-- Page-specific content goes here -->
        </main>
        
        <!-- Page Footer (optional) -->
        <footer class="page-footer">
            <!-- Footer content, credits, etc. -->
        </footer>
    </div>
    
    <!-- Page-specific JavaScript -->
    <script src="../js/some-page-script.js"></script>
</body>
</html>
```

### Key Classes

#### `.page-container`
- Main wrapper for page content
- Applies consistent max-width and centering
- Provides padding on all sides
- Sets minimum height to prevent content jump
- Background color from CSS variables

#### `.page-header`
- Consistent header styling for all pages
- Height: 4rem (64px)
- Display: flex with justify-content: space-between and align-items: center
- Border-bottom: 1px solid var(--border-color)
- Background: var(--bg-primary)
- Contains:
  - Page title (`.page-title`)
  - Action buttons (`.page-actions`)
  - Breadcrumbs (`.page-breadcrumbs`)

#### `.page-content`
- Main content area
- Flex: 1 (takes remaining vertical space)
- Padding: var(--space-6) top/bottom, var(--space-4) sides
- Overflow-y: auto for long content
- Gap: var(--space-4) between sections

#### `.page-footer` (optional)
- Consistent footer styling
- Height: 3rem (48px)
- Border-top: 1px solid var(--border-color)
- Background: var(--bg-secondary)
- Display: flex with justify-content: center and align-items: center
- Font-size: var(--font-sm)
- Color: var(--text-muted)

## Component Styles

### Page Header Elements

#### `.page-title`
- Font-size: var(--font-xl)
- Font-weight: var(--font-weight-semibold)
- Color: var(--text-primary)
- Margin: 0
- Line-height: var(--line-height-snug)

#### `.page-actions`
- Display: flex
- Gap: var(--space-2)
- Align-items: center
- Contains action buttons (`.btn`, `.btn-icon`)

#### `.page-breadcrumbs`
- Display: flex
- Gap: var(--space-1)
- Align-items: center
- Font-size: var(--font-sm)
- Color: var(--text-muted)

#### `.breadcrumb-item`, `.breadcrumb-separator`
- Standard breadcrumb styling
- Current page item: `.breadcrumb-item--current')

### Content Sections

#### `.section`
- Margin-bottom: var(--space-8)
- Last child: margin-bottom: 0

#### `.section-header`
- Display: flex
- Justify-content: space-between
- Align-items: center
- Margin-bottom: var(--space-4)
- Padding-bottom: var(--space-2)
- Border-bottom: 1px solid var(--border-color)

#### `.section-title`
- Font-size: var(--font-lg)
- Font-weight: var(--font-weight-semibold)
- Color: var(--text-primary)
- Margin: 0

#### `.section-actions`
- Display: flex
- Gap: var(--space-2)
- Align-items: center

### Cards & Panels (Page-specific variants)
While basic card styling is in globals.css, page-theme.css provides page-specific enhancements:

#### `.page-card`
- Extends `.card` from globals.css
- Border: none (relies on box-shadow for separation)
- Box-shadow: var(--shadow-md)
- Transition: box-shadow var(--transition-normal)
- Hover effect: box-shadow: var(--shadow-lg)

#### `.page-card-header`
- Padding: var(--space-4) var(--space-5)
- Border-bottom: 1px solid var(--border-color)
- Background: var(--bg-secondary)

#### `.page-card-body`
- Padding: var(--space-5)

#### `.page-card-footer`
- Padding: var(--space-4) var(--space-5)
- Border-top: 1px solid var(--border-color)
- Background: var(--bg-secondary)

### Tables
#### `.table`
- Width: 100%
- Border-collapse: collapse
- Margin-top: var(--space-3)

#### `.table-header`
- Background: var(--bg-tertiary)
- Font-weight: var(--font-weight-semibold)
- Text-align: left
- Padding: var(--space-3) var(--space-4)
- Border-bottom: 2px solid var(--border-color)

#### `.table-cell`
- Padding: var(--space-3) var(--space-4)
- Border-bottom: 1px solid var(--border-color)
- Vertical-align: middle

#### `.table-row:hover`
- Background: var(--bg-secondary)

#### `.table-stripped .table-row:nth-child(even)`
- Background: var(--bg-secondary)

### Forms (Page-specific enhancements)
#### `.form-group`
- Margin-bottom: var(--space-4)

#### `.form-label`
- Display: block
- Margin-bottom: var(--space-1)
- Font-weight: var(--font-weight-medium)
- Font-size: var(--font-sm)
- Color: var(--text-secondary)

#### `.form-help-text`
- Display: block
- Margin-top: var(--space-1)
- Font-size: var(--font-xs)
- Color: var(--text-muted)

#### `.form-row`
- Display: flex
- Gap: var(--space-3)
- Margin-bottom: var(--space-4)
- Align-items: end (for consistent baseline)

### Lists
#### `.list`
- List-style: none
- Padding: 0
- Margin: 0

#### `.list-item`
- Padding: var(--space-3) var(--space-4)
- Border-bottom: 1px solid var(--border-color)
- Display: flex
- Justify-content: space-between
- Align-items: center

#### `.list-item:last-child`
- Border-bottom: 0

#### `.list-item-content`
- Display: flex
- Flex: 1
- Align-items: center
- Gap: var(--space-3)

#### `.list-item-actions`
- Display: flex
- Gap: var(--space-2)
- Align-items: center

### Data Display

#### `.stat-card`
- Background: var(--bg-primary)
- Border: 1px solid var(--border-color)
- Border-radius: var(--radius-lg)
- Padding: var(--space-4)
- Box-shadow: var(--shadow-sm)
- Transition: var(--transition-normal)
- Hover effect: transform: translateY(-2px); box-shadow: var(--shadow-md)

#### `.stat-value`
- Font-size: var(--font-2xl)
- Font-weight: var(--font-weight-bold)
- Color: var(--text-primary)
- Line-height: var(--line-height-snug)

#### `.stat-label`
- Font-size: var(--font-sm)
- Font-weight: var(--font-weight-medium)
- Color: var(--text-muted)
- Margin-top: var(--space-1)

#### `.stat-icon`
- Font-size: var(--font-xl)
- Width: 2rem
- Height: 2rem
- Display: flex
- Align-items: center
- Justify-content: center
- Border-radius: var(--radius-lg)
- Background: var(--bg-tertiary)

### Tags & Badges
#### `.tag`
- Display: inline-flex
- Align-items: center
- Gap: var(--space-1)
- Padding: var(--space-1) var(--space-2)
- Font-size: var(--font-xs)
- Font-weight: var(--font-weight-medium)
- Border-radius: var(--radius-full)
- Background: var(--bg-tertiary)
- Color: var(--text-secondary)

#### `.tag-colored`
- Background: var(--primary)
- Color: white

#### `.badge`
- Display: inline-flex
- Align-items: center
- Justify-content: center
- Width: 1.75rem
- Height: 1.75rem
- Font-size: var(--font-xs)
- Font-weight: var(--font-weight-bold)
- Border-radius: var(--radius-full)
- Color: white

#### `.badge-primary`
- Background: var(--primary)

#### `.badge-success`
- Background: var(--success)

#### `.badge-warning`
- Background: var(--warning)

#### `.badge-danger`
- Background: var(--danger)

#### `.badge-info`
- Background: var(--info)

### Empty States
#### `.empty-state`
- Text-align: center
- Padding: var(--space-12) var(--space-4)
- Color: var(--text-muted)

#### `.empty-state-icon`
- Font-size: var(--font-3xl)
- Margin-bottom: var(--space-4)
- Color: var(--border-color)

#### `.empty-state-title`
- Font-size: var(--font-lg)
- Font-weight: var(--font-weight-semibold)
- Color: var(--text-primary)
- Margin-bottom: var(--space-2)

#### `.empty-state-description`
- Font-size: var(--font-base)
- Line-height: var(--line-height-relaxed)
- Margin-bottom: var(--space-4)

#### `.empty-state-actions`
- Display: flex
- Justify-content: center
- Gap: var(--space-2)

### Loading States
#### `.skeleton`
- Background: linear-gradient(
    90deg,
    var(--bg-secondary) 25%,
    var(--border-color) 50%,
    var(--bg-secondary) 75%
  );
- Background-size: 200% 100%;
- Animation: loading-shimmer 1.5s infinite;
- Border-radius: inherit;

#### `@keyframes loading-shimmer`
- 0%: background-position: 200% 0
- 100%: background-position: -200% 0

#### `.skeleton-text`
- Height: var(--font-base)
- Margin-bottom: var(--space-2)

#### `.skeleton-title`
- Height: calc(var(--font-lg) * 1.2)
- Margin-bottom: var(--space-3)

#### `.skeleton-avatar`
- Width: 2rem
- Height: 2rem
- Border-radius: var(--radius-full)

## Interactive Elements

### Buttons (Page-specific variants)
#### `.page-btn`
- Extends base button styles
- Font-weight: var(--font-weight-semibold)
- Transition: all var(--transition-normal)
- Hover effect: transform: translateY(-1px)

#### `.page-btn-icon`
- Width: 2.25rem
- Height: 2.25rem
- Border-radius: var(--radius-lg)
- Display: flex
- Align-items: center
- Justify-content: center
- Font-size: var(--font-lg)

### Inputs & Form Elements (Page-specific)
#### `.page-input`
- Extends base input styles
- Font-size: var(--font-lg)
- Padding: var(--space-3) var(--space-4)

#### `.page-textarea`
- Extends base textarea styles
- Font-size: var(--font-lg)
- Padding: var(--space-3) var(--space-4)
- Min-height: 8rem

#### `.page-select`
- Extends base select styles
- Font-size: var(--font-lg)
- Padding: var(--space-3) var(--space-4)

### Navigation
#### `.page-nav`
- Display: flex
- Gap: var(--space-3)
- Align-items: center
- Flex-wrap: wrap

#### `.page-nav-link`
- Padding: var(--space-2) var(--space-3)
- Border-radius: var(--radius-md)
- Font-weight: var(--font-weight-medium)
- Color: var(--text-secondary)
- Transition: var(--transition-normal)
- Text-decoration: none

#### `.page-nav-link:hover`
- Background: var(--bg-tertiary)
- Color: var(--text-primary)

#### `.page-nav-link-active`
- Background: var(--primary)
- Color: white

## Responsive Behavior

### Breakpoints
Follows mobile-first approach with these breakpoints in media queries:
- sm: 640px
- md: 768px
- lg: 1024px
- xl: 1280px

### Page-layout Responsiveness
- `.page-container`: 
  - Padding: var(--space-4) on all sides (mobile)
  - Padding: var(--space-6) on sides (lg+)
  - Max-width: 100% (mobile), 1200px (lg+)
  
- `.page-header`:
  - Flex-direction: column (sm and below)
  - Align-items: stretch (sm and below)
  - Gap: var(--space-3) (sm and below)
  - Flex-direction: row (md+)
  - Align-items: center (md+)
  - Gap: var(--space-4) (md+)
  
- `.page-actions`:
  - Margin-top: var(--space-2) (sm and below)
  - Margin-top: 0 (md+)
  - Margin-left: auto (md+)

### Component Responsiveness
- Cards and sections stack vertically on small screens
- Tables become scrollable horizontally on small screens
- Form elements expand to full width on small screens
- Navigation adapts to available space

## Animation & Transitions

### Page Transitions
- Fade-in: opacity 0 → 1 over 150ms
- Slide-up: translateY(10px) → 0 over 200ms
- Scale-in: scale(0.95) → 1 over 150ms

### Interactive Feedback
- Button press: scale(0.97) on active state
- Card lift: translateY(-2px) on hover
- Input focus: scale(1.01) subtle effect

## Printing Styles

### @media print
- Removes background colors (saves ink)
- Increases contrast for text
- Hides interactive elements (buttons, etc.)
- Forces page breaks on major sections
- Shows URLS for links

## Dark Mode Preparation
While currently designed for light mode, the CSS uses variables that could support dark mode:
- All colors defined as CSS variables
- Semantic naming (--text-primary, --bg-primary) vs specific colors
- Easy to override variables for dark theme
- Media query prefers-color-scheme ready for future implementation

## Accessibility Features

### Focus Styles
- Visible focus outlines on all interactive elements
- Focus ring: 3px solid var(--primary) with 2px offset
- Outline-offset: 2px

### Color Contrast
- Text/background ratios meet WCAG AA
- Interactive elements have sufficient contrast
- Placeholder text meets contrast requirements

### Touch Targets
- Minimum 44x44px for interactive elements
- Adequate spacing between touch targets

### Screen Reader Support
- Semantic HTML structure encouraged
- ARIA labels recommended for icons
- Logical tab order in components

### Reduced Motion
- Respects prefers-reduced-media: reduce
- Animations disabled or simplified when requested

## Usage Guidelines

### When to Use page-theme.css
- Use on all standalone pages (not embedded components)
- Provides consistent chrome and layout
-application-wide consistent look and feel or header/footer styling needed
- Particularly useful for: dashboard, settings, tasks, calendar, email, notes, memory, research, agents pages

### Extending the Theme
When adding new page-specific styles:
1. Consider if they belong in globals.css (truly reusable)
2. If page-specific, add to page-theme.css with clear naming
3. Use BEM-like naming: `.block__element--modifier`
4. Add responsive considerations
5. Consider accessibility implications

### Customization
To customize the page theme:
1. Modify values in the CSS variables (preferably through globals.css)
2. Override specific selectors as needed
3. Consider creating theme variants (dark mode, high contrast, etc.)
4. Maintain consistency with existing patterns

## Implementation Examples

### Dashboard Page
```html
<div class="page-container">
    <header class="page-header">
        <h1 class="page-title">Dashboard</h1>
        <div class="page-actions">
            <button class="btn btn-primary">New Task</button>
            <button class="btn btn-icon" title="Refresh">
                <i class="icon-refresh"></i>
            </button>
        </div>
    </header>
    
    <main class="page-content">
        <section class="section">
            <div class="section-header">
                <h2 class="section-title">Today's Overview</h2>
            </div>
            <div class="stat-grid">
                <!-- Stat cards -->
            </div>
        </section>
        
        <section class="section">
            <div class="section-header">
                <h2 class="section-title">Upcoming Tasks</h2>
                <div class="section-actions">
                    <button class="btn btn-outline">View All</button>
                </div>
            </div>
            <div class="task-list">
                <!-- Task items -->
            </div>
        </section>
    </main>
    
    <footer class="page-footer">
        <small>Mindbase © 2026</small>
    </footer>
</div>
```

### Settings Page
```html
<div class="page-container">
    <header class="page-header">
        <h1 class="page-title">Settings</h1>
    </header>
    
    <main class="page-content">
        <section class="section">
            <div class="section-header">
                <h2 class="section-title">General Settings</h2>
            </div>
            <div class="form-group">
                <label class="form-label" for="app-name">Application Name</label>
                <input class="page-input" type="text" id="app-name" value="Mindbase">
                <p class="form-help-text">This appears in the application header</p>
            </div>
            
            <div class="form-group">
                <label class="form-label" for="timezone">Time Zone</label>
                <select class="page-select" id="timezone">
                    <!-- Options -->
                </select>
                <p class="form-help-text">Used for timestamp display</p>
            </div>
        </section>
        
        <section class="section">
            <div class="section-header">
                <h2 class="section-title">Appearance</h2>
            </div>
            <!-- Appearance controls -->
        </section>
    </main>
</div>
```

## Performance Considerations

### CSS Efficiency
- Uses efficient selectors (avoids overly complex descendant selectors)
- Leverages CSS variables for easy theming
- Minimizes use of !important
- Groups related styles together

### Loading Strategy
- Loaded after globals.css (dependencies correct)
- Can be combined with globals.css for production
- Critical CSS consideration: above-the-fold styles could be inlined
- Uses media queries appropriately for responsive loading

### Rendering Performance
- Minimizes layout thrashing
- Uses transform and opacity for animations where possible
- Will-change properties considered for animated elements
- Efficient use of flexbox and grid layouts

## Maintenance Guidelines

### Adding New Styles
1. Determine if style is truly reusable (→ globals.css) or page-specific
2. Follow existing naming conventions
3. Add responsive variants at appropriate breakpoints
4. Consider accessibility implications
5. Add comments for complex selectors
6. Ensure consistent formatting with existing code

### Removing Styles
1. Verify no pages are using the selector
2. Consider if it might be needed in future
3. Remove associated responsive variants
4. Update documentation if necessary

### Testing Changes
1. Test on multiple pages that use the theme
2. Check various screen sizes (mobile, tablet, desktop)
3. Verify interactive states (hover, focus, active)
4. Test with actual content (long text, images, etc.)
5. Verify printing appearance
6. Check accessibility with screen readers and keyboard navigation

## Dependencies

### Requires globals.css
- All color and spacing variables come from globals.css
- Base component styles (buttons, inputs, cards) defined in globals.css
- Utility classes defined in globals.css

### Used By
All standalone HTML pages in `frontend/pages/`:
- dashboard.html
- tasks.html
- calendar.html
- email.html
- notes.html
- memory.html
- research.html
- agents.html
- settings.html

### JavaScript Interaction
- JavaScript may add/remove classes (e.g., active states)
- CSS transitions work with class changes
- Animation classes can be toggled via JS
- Custom properties can be read/modified via JS if needed

## Browser Support
- Targets modern evergreen browsers
- Uses CSS custom properties (IE11 not supported)
- Flexbox and grid layout used extensively
- Fallbacks not provided for legacy browsers
- Mobile-first responsive design

## Future Considerations

### Dark Mode
- Current structure supports easy dark mode implementation
- Would involve overriding CSS variables in @media (prefers-color-scheme: dark)
- Could add theme toggle in settings

### Theme Customization
- Potential for user-customizable themes
- Could expose color picker for accent color
- Could allow saving custom themes

### Component Library Evolution
- Consider migrating to CSS-in-JS or styled components for dynamic theming
- Could adopt utility-first approach (like Tailwind) for more flexibility
- Could add more sophisticated animation system