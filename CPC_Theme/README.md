# Cobalt Prairie Consulting Application Theme

This folder is a framework-aware visual reference package for Cobalt Prairie Consulting applications. It contains only design guidance, reusable CSS, and static HTML examples. Do not import application logic, routes, API calls, IDs, or JavaScript from this folder.

## Files to give an AI coder

- `README.md` — implementation rules and design language.
- `theme.css` — reusable color tokens and component styling.
- `login-template.html` — canonical public login layout (uses Bootstrap 5).
- `app-shell-template.html` — canonical authenticated application shell (framework-neutral classes).

## Brand language

The visual system combines deep cobalt/navy surfaces with restrained gold accents, white content surfaces, slate secondary text, generous spacing, and compact professional controls.

### Core colors

| Token | Value | Use |
|---|---|---|
| Navy | `#0d1b2a` | Navigation, dark surfaces, primary text |
| Cobalt | `#1e3a8a` | Hero gradients and supporting brand surfaces |
| Gold | `#c89b5e` | Primary actions, focus rings, accents |
| Gold hover | `#d2aa74` | Hover state for gold controls |
| Light background | `#f5f6f7` | Public form panels and app background |
| Border | `#dfe3e8` | Inputs, cards, separators |
| Slate 300 | `#cbd5e1` | Text on dark backgrounds |
| Slate 400 | `#94a3b8` | Secondary text on dark backgrounds |
| Danger | `#dc3545` | Errors and destructive actions |
| Success | `#198754` | Confirmation messages |

## Typography

Use Inter with native system fallbacks:

```css
font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
```

Recommended weights are 400 for body copy, 500 for controls, 600 for section labels, and 700 for major headings.

## Public login layout

The canonical login page is a full-height split layout. The recommended implementation assumes Bootstrap 5 is available in the target application.

- Left side: `col-12 col-lg-7` using the `.hero-gradient` class.
- Right side: `col-12 col-lg-5` with an inline `background: #f5f6f7`.
- Include CPC branding, application name, a short product statement, and up to four concise features.
- Feature icons must be professional line SVGs (stroke-width 2) centered in `.feature-icon` (44px square gold-tint containers).
- Right side centers a white form card no wider than 420px using `.shadow-soft` and `.rounded-4xl`.
- Inputs use Bootstrap `.form-control`, white background, navy text, and gold focus.
- Primary authentication action is a full-width gold pill button (`.btn-gold .rounded-pill`).
- Secondary actions (registration, password recovery) can be stacked as `.btn-outline-gold` pill buttons or as small centered text links.
- Do not show a light/dark theme control before authentication.
- Below the `lg` breakpoint, the hero and form stack vertically.

### Required utility classes

These classes are provided in `theme.css` and used by `login-template.html`:

- `.hero-gradient` — navy-to-cobalt diagonal gradient.
- `.text-gold`, `.text-slate-300`, `.text-slate-400` — brand text colors.
- `.btn-gold`, `.btn-outline-gold` — primary/secondary actions.
- `.shadow-soft` — 0 20px 60px rgba(13, 27, 42, 0.08).
- `.rounded-4xl` — 1.75rem border radius.
- `.tracking-widest` — uppercase eyebrow letter spacing.
- `.feature-icon` — 44px icon container.

## Authenticated application shell

- Use a 58px navy/cobalt top navigation bar with a subtle gold divider (`.cpc-topbar`).
- Put the application name at the left in gold (`.cpc-brand`).
- Use compact outlined controls in the top bar (`.cpc-btn-secondary`).
- Theme controls may appear only after authentication.
- Use white/light panels in light mode and navy panels in dark mode (`.cpc-panel`).
- Section labels use uppercase gold text with increased letter spacing (`.cpc-section-label`).
- Primary content should remain the visual focus; avoid decorative gradients outside branded navigation and login hero areas.

## Components

### Buttons

- Primary: gold background, navy text, semibold, pill radius.
- Secondary: transparent background, neutral border, 7px radius.
- Secondary hover: faint gold background and gold border.
- Destructive: red treatment reserved for irreversible actions.

### Forms

- Inputs use a white or theme-surface background and 7px radius.
- Focus state uses a gold border and `0 0 0 0.2rem rgba(200, 155, 94, 0.25)` ring.
- Labels are compact and muted.
- Validation errors appear below the relevant form area in red.

### Cards and dialogs

- Cards use white or theme panel backgrounds, subtle borders, and restrained shadows.
- Standard card radius is 12px; authentication cards use 28px (`.rounded-4xl`).
- Dialog headers use navy with white text.

### Tables and tabs

- Table headers use navy with white text.
- Active tabs use gold with navy text.
- Keep row treatments subtle and preserve high contrast.

## Accessibility and behavior

- Maintain WCAG-friendly contrast.
- Every input must have an associated label.
- SVG icons should use `aria-hidden="true"` when decorative.
- Preserve visible keyboard focus states.
- Never use color as the only status indicator.
- Keep interactive targets at least 36px high where practical.
- Do not add remote runtime dependencies solely for theming; copy needed assets into the target application.

## Implementation workflow

1. Copy `theme.css` into the target application's own static asset directory.
2. Include Bootstrap 5 in the target application if using the login template.
3. Map the application's existing structure to the classes demonstrated in the templates.
4. Replace placeholder product copy and route URLs.
5. Keep all application-specific JavaScript and API behavior in the target application.
6. Validate desktop and mobile layouts.
7. Confirm theme controls are unavailable before login and available in the authenticated shell only.
