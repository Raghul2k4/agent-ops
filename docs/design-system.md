# AgentOps — Design System

**Scope:** the implemented M0 + M1 interface. Later modules reuse these primitives; they do not
introduce a parallel styling approach.

**Source of truth:** [`apps/web/src/styles/index.css`](../apps/web/src/styles/index.css) (tokens),
[`apps/web/src/components/ui`](../apps/web/src/components/ui) (primitives),
[`apps/web/src/components/layout`](../apps/web/src/components/layout) (shell).

---

## 1. Principles

1. **Dark-first, light supported.** Dark navy-charcoal surfaces are the default; the light theme is
   a deliberate token set, not an inversion hack.
2. **Semantic tokens only.** Components reference `--surface`, `--border`, `--primary`, … Never a
   raw hex value in a component.
3. **Density with air.** Developer tooling is information-dense, but hierarchy is carried by
   typography, spacing and surface layering — not by colour noise.
4. **Motion explains state.** Transitions are short and functional; nothing animates perpetually.
5. **Accessible by default.** Visible focus, semantic HTML, contrast-checked pairs, status conveyed
   with text as well as colour, `prefers-reduced-motion` respected.

---

## 2. Colour tokens

Defined for `:root` (dark) and `[data-theme="light"]`. Values are the current implementation; the
names are the contract.

| Token | Dark | Light | Use |
|---|---|---|---|
| `--background` | `#0a0e14` | `#f6f8fb` | App canvas |
| `--foreground` | `#e7eef7` | `#0f1720` | Primary text |
| `--surface` | `#10161f` | `#ffffff` | Panels, sidebar rows |
| `--surface-elevated` | `#161d28` | `#ffffff` | Cards, dialogs |
| `--surface-muted` | `#1b2330` | `#eef2f7` | Inputs, table headers, hover |
| `--border` | `#232c3a` | `#d8dee8` | Dividers, control outlines |
| `--border-strong` | `#33405280` | `#b9c3d1` | Emphasis borders |
| `--primary` | `#58a6ff` | `#1f6feb` | Primary action, links, focus |
| `--primary-foreground` | `#04101f` | `#ffffff` | Text on primary |
| `--primary-muted` | `#58a6ff1f` | `#1f6feb14` | Selected rows, badges |
| `--secondary` | `#8b7cf6` | `#6d5ce0` | Secondary accent (violet) |
| `--success` | `#34d399` | `#0f9d58` | Successful runs, positive deltas |
| `--warning` | `#fbbf24` | `#b45309` | Needs attention, degraded |
| `--danger` | `#f87171` | `#d33a3a` | Failed runs, destructive actions |
| `--muted` | `#1b2330` | `#eef2f7` | Disabled fills |
| `--muted-foreground` | `#8d9bb0` | `#5b6879` | Secondary text, metadata |
| `--focus-ring` | `#58a6ff` | `#1f6feb` | `:focus-visible` outline |

Each status colour has a `-muted` companion for tinted backgrounds. **Never** use a status colour as
the only signal: pair it with a label or an icon.

Tailwind v4 maps tokens to utilities (`--color-background` → `bg-background`, etc.), so
`bg-surface`, `text-muted-foreground`, `border-border` and `ring-focus-ring` are the day-to-day API.

---

## 3. Typography

| Role | Font | Notes |
|---|---|---|
| UI | Inter (`'Segoe UI'` fallback) | `font-feature-settings: 'cv02','cv03','cv04','ss01'` |
| Mono | JetBrains Mono (`Cascadia Code` fallback) | IDs, traces, JSON, code |

- Body: 14–16 px, line-height 1.5–1.6.
- Page title: 20–24 px, weight 600. Section title: 15–16 px, weight 600. Labels: 12–13 px,
  weight 500, `--muted-foreground`.
- Numerals in metrics and tables use `font-variant-numeric: tabular-nums`.
- Headings stay restrained; the hierarchy is size + weight + colour, not decoration.
- Long identifiers wrap or scroll inside a mono block — they never widen the page.

---

## 4. Spacing, radii, elevation

| Token | Value |
|---|---|
| `--radius-sm` | 6 px |
| `--radius-md` | 9 px |
| `--radius-lg` | 13 px |
| `--shadow-sm` | `0 1px 2px rgb(0 0 0 / .4)` |
| `--shadow-md` | `0 8px 24px -12px rgb(0 0 0 / .65)` |
| `--shadow-lg` | `0 24px 60px -24px rgb(0 0 0 / .8)` |

Spacing follows a 4 px base scale (4/8/12/16/24/32/48). Card padding is 16–24 px; page gutters are
24 px desktop, 16 px tablet, 12 px mobile. Elevation is used for overlays and elevated cards only —
not on every panel.

---

## 5. Components (implemented)

| Component | File | Notes |
|---|---|---|
| Button | `ui/button.tsx` | Variants: primary, secondary, ghost, danger; sizes sm/md; loading state; icon-only requires `aria-label` |
| Input | `ui/input.tsx` | Same height as buttons; invalid state uses `aria-invalid` + `--danger` |
| Field | `ui/field.tsx` | Label + description + error, wired with `htmlFor`/`aria-describedby` |
| Card | `ui/card.tsx` | `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent` |
| Badge | `ui/badge.tsx` | Neutral / primary / success / warning / danger; text always present |
| States | `ui/states.tsx` | `EmptyState`, `ErrorState`, `LoadingState` (skeletons) |
| Error boundary | `ui/error-boundary.tsx` | Route-level fallback with retry, no stack traces in UI |
| App shell | `layout/app-shell.tsx` | Sidebar + top bar + content, skip link |
| Sidebar | `layout/sidebar.tsx` | Primary navigation, collapsible, active state |
| Top bar | `layout/topbar.tsx` | Breadcrumbs, workspace switcher, search trigger |
| Workspace switcher | `layout/workspace-switcher.tsx` | Lists the caller's workspaces; disabled when empty |
| Command palette | `layout/command-palette.tsx` | `Ctrl/Cmd+K`; navigation/actions only, no unauthorized entries |

Planned primitives for later milestones: table + pagination, tabs, dialog, dropdown, toast,
tooltip, code/JSON viewer, trace timeline, workflow nodes, model selector, approval card, date
filters. Each is added to `components/ui` (or the owning feature) — not duplicated per screen.

---

## 6. Layout

```
┌──────────────────────────────────────────────────────────┐
│ Top bar: breadcrumbs · workspace switcher · search · user │
├────────────┬─────────────────────────────────────────────┤
│ Sidebar    │ Page header (title, description, actions)    │
│ (primary   │ ───────────────────────────────────────────  │
│ navigation)│ Content: cards, tables, forms, canvas        │
│            │                                              │
└────────────┴─────────────────────────────────────────────┘
```

- Max content width ~1280 px, centred, with consistent gutters.
- Inspector panels (run details, node config) are right-side and resizable where they exist.
- **Responsive:** ≥1024 px full shell; 768–1023 px condensed sidebar; <768 px sidebar becomes a
  drawer, tables scroll horizontally inside their own container, and the page never introduces a
  horizontal body scrollbar.
- Keyboard order follows visual order; the first tab stop is a “Skip to content” link.

---

## 7. Motion

| Interaction | Duration / easing |
|---|---|
| Hover, focus | 120–150 ms, `ease-out` |
| Sidebar / drawer | 180–220 ms, `ease-out` |
| Dialog / overlay | 150–200 ms, opacity + 4 px translate |
| Toast | 150 ms in, 120 ms out |
| Skeleton | Subtle pulse, disabled under reduced motion |

`@media (prefers-reduced-motion: reduce)` removes transforms and non-essential animation. Active
work uses a real progress indicator tied to state, not a decorative loop on every card.

---

## 8. States every screen must handle

| State | Treatment |
|---|---|
| Initial load | Skeletons matching the final layout |
| Empty | `EmptyState` with one clear next action |
| No search results | “No matches” + clear-filter action |
| Success | Content, with counts and timestamps |
| API failure | `ErrorState` with a safe message and retry |
| Permission denied | Explicit explanation; no data leak |
| Expired session | Re-authenticate prompt; token cleared |
| Validation error | Inline field error + summary |
| Long-running | Progress, elapsed time, cancel where supported |
| Partial / cancelled | Distinct status, completed steps preserved |
| Offline / provider down | Named dependency and a retry path |

No screen is left blank because a request failed.

---

## 9. Accessibility checklist

- Semantic landmarks (`header`, `nav`, `main`, `aside`) and one `h1` per page.
- All controls reachable and operable by keyboard; focus visible via `--focus-ring`.
- Icon-only buttons have `aria-label`; images have `alt`; decorative art is `aria-hidden`.
- Dialogs trap focus, restore it on close, and close on `Escape`.
- Status is announced (`role="status"` / `aria-live="polite"`), not only coloured.
- Form errors reference the field with `aria-describedby`.
- Contrast targets: 4.5:1 for body text, 3:1 for large text and UI boundaries.
- Charts have a textual summary or an equivalent table (from M5 onward).
- `prefers-reduced-motion` honoured.

---

## 10. Rules for contributors

1. Add a token instead of a literal colour; add a primitive instead of a one-off button.
2. Reuse `Field` for every input so labels and errors stay wired.
3. Every new screen implements loading, empty, error and success states.
4. No icon-only control without an accessible name.
5. No placeholder action: a control either works or is visibly disabled with a reason.
6. Keep the shell consistent — new pages plug into `AppShell`, they do not repaint the frame.
