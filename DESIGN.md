# Engineering Guard Factory Dashboard — Design System

## Visual Direction
**Era:** Contemporary software engineering tools (VS Code, GitHub, Linear, Vercel)
**Tone:** Professional, direct, minimal; trust the data over decoration
**Movement:** Subtle: hover states, status transitions, careful attention cues
**Priority:** Information density + breathing room; scanability + completeness

## Color Palette
```
Semantic:
  --pass:       #10b981  (emerald, success)
  --changes:    #f59e0b  (amber, warning/needs work)
  --pending:    #d1d5db  (slate, in-progress)
  --na:         #9ca3af  (gray, not applicable)
  --human:      #0f766e  (teal, requires human decision)
  --danger:     #ef4444  (red, error/invalid)

Neutral:
  --bg:         #f9fafb  (gray-50, page background)
  --bg-raised:  #ffffff  (white, card/elevated surfaces)
  --border:     #e5e7eb  (gray-200, dividers and strokes)
  --text-primary: #111827 (gray-900, body text)
  --text-muted:   #6b7280 (gray-500, secondary, labels)
  --hover-bg:     #f3f4f6 (gray-100, interactive hover)

Interactive:
  --focus:      #3b82f6  (blue, focus ring)
  --link:       #0284c7  (blue-600, links)
```

## Typography
```
Font family: system-ui, -apple-system, sans-serif
  (system fonts; Segoe UI on Windows, SF Pro Display on Mac, Roboto on Android)

Scale:
  Display (h1):  18px/1.2, 700/600 weight, +0.02em letter-spacing
  Heading (h2):  14px/1.3, 700 weight
  Label (h3):    13px/1.4, 600 weight, 0.06em uppercase letter-spacing
  Body:          13px/1.5, 400 weight (increased from 14px in current)
  Small:         12px/1.4, 400 weight (secondary text, stats)
  Tiny:          11px/1.3, 500 weight (metadata, status chips)

Line-height:
  Headings:  1.2–1.3 (tight for impact)
  Body text: 1.5 (readable in modal content)
  Labels:    1.4 (clarity in crowded spaces)
```

## Spacing System
```
Base: 4px grid
  2px:  micro borders, tiny gaps
  4px:  base unit
  8px:  component padding, small gaps
  12px: medium spacing
  16px: standard padding, section gaps
  20px: larger spacing
  24px: page padding, major sections
  32px: huge gaps, hero spacing
```

## Components

### Cards
**Context:** Pipeline job cards, compact yet informative
**States:**
- Default: white bg, gray-200 border, subtle hover lift
- Hover: border lightens, shadow appears, cursor pointer
- Attention (needs human): teal border and a teal-tinted top of the card

**Content hierarchy:**
```
┌─────────────────────────────┐
│ [Status Badge] Job ID       │  (12px, muted, right-aligned badge)
├─────────────────────────────┤
│ Job Title                   │  (13px, 600 weight, tighter spacing)
├─────────────────────────────┤
│ Repository / Path (if rel.) │  (11px, muted, optional)
├─────────────────────────────┤
│ Round R1 | tests: ● reviews:│  (11px, semantic chips inline)
│           ● security ● ux   │
├─────────────────────────────┤
│ ⚠ Warning message (if any)  │  (11px, danger/warning color)
└─────────────────────────────┘
```

**Sizing:**
- Desk (1920px): 3-4 columns, ~280px per card
- Tablet (768px): 2 columns
- Mobile (360px): 1 column, full-width with side padding

### Status Badges / Chips
**Spec stage:** gray background, dark text
**Spec Review / Needs Human:** teal column header and flag icon
**Other stages:** subtle bg, muted text
**Verdict chips (in card & modal):**
  - Test audit: `tests` label + verdict color
  - Reviewer chips: `security`, `ux`, `ui`, `code`, `architecture` + verdict (the architecture chip is hidden on rounds recorded before that reviewer existed)
  - STRIDE: `stride` + verdict
  All: 11px, 500 weight, 8px horizontal padding, 2px vertical

### Modal (File Viewer)
**Trigger:** click job card
**Layout:**
```
┌─────────────────────────────────────────────────┐
│ [File Tabs] ... ... [Close]                     │  16px padding, gray-200 border-bottom
├─────────────────────────────────────────────────┤
│                                                 │
│ Markdown content (16px padding)                 │
│ Full-width, scrollable, with breathing room    │
│ Monospace code blocks, tables, blockquotes      │
│ Links blue, headings prominent                  │
│                                                 │
└─────────────────────────────────────────────────┘
```
- Tab styling: active = dark bg, white text; inactive = white bg, gray border
- Smooth reveal animation on file load (fade-in, no jank)

## Layout Patterns

### Page Structure
```
┌─────────────────────────────────────────────────────────────┐
│ [Logo] Factory Status: [count + last-update]                │  Header
├─────────────────────────────────────────────────────────────┤
│ ☝ [Quick Stats Row] or [Global Filter/Sort Controls]        │  Optional
├─────────────────────────────────────────────────────────────┤
│ [Tab: In Progress] [Tab: Archive]  [Segment: All/Human]    │  Navigation
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Repository / Stage Grouping]                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │  Jobs Container
│  │  Card 1  │ │  Card 2  │ │  Card 3  │                    │  Grid, auto-flow
│  └──────────┘ └──────────┘ └──────────┘                    │
│                                                             │
│  [Another group if needed]                                 │
│  ┌──────────┐ ┌──────────┐                                 │
│  │  Card 4  │ │  Card 5  │                                 │
│  └──────────┘ └──────────┘                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Header
- Flex row, 24px padding, gray-50 bg, gray-200 border-bottom
- Logo/title on left (18px, 700 weight)
- Status text on right (13px muted): `{count} jobs · updated 10:32:45 AM`
- On mobile: stack or hide status behind expandable badge

### Navigation Tabs
- Horizontal flex, no margin
- Each tab: 13px, 600 weight, tall padding (12px vert, 16px horiz)
- Active: dark text + dark bottom border (2px)
- Inactive: muted text, no border
- Optional: expand to include filter chips (e.g., "All", "Needs Human", "Blocked")

### Job Grid
- `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`
- `gap: 16px` (increased from 12px for breathing room)
- Responsive: auto-fills available space, no fixed column count

### Markdown in Modal
- Code blocks: gray-100 bg, gray-900 text, 12px monospace, 12px padding, light border
- Tables: clean borders, gray-100 header bg, alternating row colors optional
- Blockquotes: left border (3px, gray-300), italic, muted text, inset padding
- Lists: standard ul/ol, 1.4em indent
- Paragraphs: 1.5 line-height, 0.8em margin-bottom
- Links: blue, underline on hover

## Interaction Patterns

### Job Card Click
- Open modal immediately (no delay)
- Fade in modal with shadow
- Load file list in header tab row
- Fetch and render first file
- Preserve scroll position in background (no jank on close)

### Status Update
- Poll every 2s (preserved from current)
- On new data: update cards in-place without recreating
- Highlight recently-changed items briefly (50ms pulse, optional)
- On stage change: soft transition, no jump

### Human Decision States
- Needs-human jobs: prominent card styling (teal border + bg tint)
- Click-through to approval/escalation actions (if API exists)
- Alternative: highlight with ⚠ icon, suggest next action in card subtitle

### Filter/Sort (Nice-to-Have, Phase 2)
- Quick toggles in header: "All", "Needs Human", "Failed", "In Review"
- Optional search by job title/ID
- Sort by: stage (pipeline order), last-update (newest first), status (human first)

## Responsive Breakpoints
```
Mobile (≤480px):
  - Single column grid
  - Smaller padding (12px page, 8px card)
  - Abbreviated labels on chips
  - Stacked header/tabs

Tablet (481px–768px):
  - Two column grid
  - Standard padding
  - Full labels

Desk (≥769px):
  - 3–4 column grid (auto-fill)
  - Full padding and breathing room
```

## Animation & Motion
- **Page load:** Cards fade in as data loads (200ms stagger per card)
- **Modal open:** Fade-in + subtle scale (150ms ease-out)
- **Modal close:** Reverse fade-out (100ms)
- **Hover state:** Border/shadow change (150ms ease), no jank
- **Status change:** Brief 50ms highlight pulse (optional, subtle)

## Accessibility
- Color is not the only indicator; use text labels and icons where semantic color matters
- Contrast: ≥4.5:1 on all text (WCAG AA standard)
- Focus rings: 2px outline, 2px offset, blue-500
- Tab order: natural flow, skip any non-interactive elements
- ARIA: `role="dialog"` on modal, `aria-label` on icon-only buttons, `aria-live` on status
- Keyboard: Escape closes modal, Tab cycles through focusable elements

## Overview tab
A job with a `handover.md` opens on **Overview**: a one-row status line (stage, round, verdict chips), warnings, the recommendation from `decision.md`, then the handover as a reading document. Diagrams are drawn in the current theme and redrawn on a theme change. A diagram that cannot be drawn becomes an error card with its source. Jobs without a handover open on their first file.

---

## Implementation Notes
- No CSS framework or build step; all CSS inline in `<style>` tag
- Preserve existing JS polling, markdown renderer, event handling
- Enhance with CSS grid instead of flexbox for card layout
- Keep color tokens as CSS variables for future theming
- Focus on semantic HTML structure
- Test at 320px, 768px, 1280px, 1920px viewports
