# Color Guidelines

See also: `DESIGN_SYSTEM.md`, `DESKTOP_STYLE_GUIDE.md`.

## Core palette roles

- **Primary**: main interactive emphasis.
- **Secondary**: secondary controls and accents.
- **Success**: successful operations and positive statuses.
- **Warning**: caution and pending/attention statuses.
- **Danger**: destructive/error states and blocked statuses.
- **Information**: neutral informational emphasis.
- **Background/Surface**: page and container hierarchy.
- **Hover/Selection/Disabled**: interaction and affordance states.

## Theme support

Supported runtime themes:

1. Light
2. Dark
3. Blue
4. Green
5. High Contrast

## Implementation source

- `ThemeRegistry` builds `ColorScheme` by theme identity.
- `AppSemanticColors` provides semantic tokens (`success`, `warning`, `information`).
- Components must consume `Theme.of(context).colorScheme` and `context.semanticColors`.

## Status color policy

`StatusBadge` tone mapping:

- Success: `ACTIVE`, `APPROVED`
- Warning: `PENDING`, `DRAFT`, `NEAR EXPIRY`
- Danger: `INACTIVE`, `REJECTED`, `BLOCKED`, `DELETED`, `ARCHIVED`, `EXPIRED`
- Neutral: fallback/unknown statuses
