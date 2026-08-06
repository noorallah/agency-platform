# Responsive Standards

These targets extend the Phase 1 navigation responsive rules in `DESKTOP_UI_FRAMEWORK.md` to dialogs/forms introduced in Phase 2.

| Breakpoint | Navigation | Dialog width |
|---|---|---|
| Wide monitor (≥ ~1400px) | Expanded sidebar (260px) | 88% of window width, capped at 1100px content width |
| Laptop (~1000–1400px) | Collapsible to icon rail (64px) | 88% of window width, content still capped at 1100px |
| Tablet-equivalent window | Icon rail + flyout menus | Dialog remains 88% of window; sections stack normally since they were never tab-based |
| Small window (< ~1000px) | Overlay `Drawer` navigation | Dialog still uses `insetPadding`; single-column section stacking degrades gracefully because there was never a fixed-width side panel inside the dialog to break |

## Why collapsible sections are inherently more responsive than tabs

A horizontal tab/`SegmentedButton` strip has a minimum width driven by the number of tabs; on a narrow window it either wraps awkwardly or requires horizontal scrolling. A vertical stack of collapsible `EnterpriseSection`s has no such constraint — it degrades to a taller, narrower scroll on small windows, which is exactly the small-window behavior enterprise ERPs (Fiori, Business Central) use.

## Rule

No dialog or workspace may introduce a layout that only works above a specific width. Every new Enterprise component must be tested (or at minimum reasoned through) at both the wide-monitor and narrow-window breakpoints already defined for the shell.
