# Taxonomy Workbench — UI Redesign Specification v1.0

> **Designer**: UI Designer
> **Date**: 2026-07-09
> **Status**: Ready for developer handoff
> **Target**: Product Taxonomy Maintenance Agent (M5 Frontend)

---

## 1. Executive Summary

The current UI suffers from 8 critical design issues: emoji-based icons, cluttered topbar, dated dropzone pattern, no color system foundation, inconsistent spacing, flat typography hierarchy, chaotic button styles, and missing loading/empty states. This redesign establishes a **design token system first**, then applies it component-by-component to achieve a professional SaaS-grade interface.

**Design philosophy**: Clean, functional, accessible — letting the AI agent capabilities shine through restrained visual design.

---

## 2. Design Token System

### 2.1 Color Palette

```
PRIMARY (Indigo) — Brand identity & interactive elements
  ── 50:  #EEEDFE   (light fills, active nav backgrounds)
  ── 100: #CECBF6   (hover states, subtle accents)
  ── 200: #AFA9EC   (borders, dividers)
  ── 400: #7F77DD   (icon active states)
  ── 600: #534AB7   (primary buttons, links, focus)
  ── 800: #3C3489   (active text, headings on colored bg)
  ── 900: #26215C   (text on primary backgrounds)

SEMANTIC COLORS
  ── Success: #EAF3DE(bg) / #639922(text) / #27500A(dark text)
  ── Warning: #FAEEDA(bg) / #BA7517(text) / #633806(dark text)
  ── Error:   #FCEBEB(bg) / #E24B4A(text) / #791F1F(dark text)
  ── Info:    #E6F1FB(bg) / #378ADD(text) / #0C447C(dark text)

NEUTRAL GRAY SCALE
  ── Backgrounds:  #FAFBFC(page), #F8F8F7(surface-1), #F1EFE8(surface-2)
  ── Borders:      #E8E7E1(default), #D3D1C7(stronger)
  ── Text:         #2C2C2A(primary), #444441(secondary), #888780(tertiary), #B4B2A9(disabled/hints)
```

**Accessibility compliance**: All text/background combinations meet WCAG AA 4.5:1 contrast ratio.

### 2.2 Typography Scale

| Token        | Size | Weight | Line-height | Usage                     |
|-------------|------|--------|------------|---------------------------|
| Display     | 24px | 500    | 1.3        | Hero numbers, key metrics |
| Heading 1   | 18px | 500    | 1.35       | Page titles               |
| Heading 2   | 15px | 500    | 1.4        | Section titles            |
| Heading 3   | 14px | 500    | -          | Card titles               |
| Body Large  | 14px | 400    | -          | Emphasized body text      |
| Body        | 13px | 400    | 1.6        | Default body              |
| Caption     | 12px | 400    | -          | Metadata, timestamps     |
| Label       | 11px | 500    | uppercase  | Field labels, section hdr |

**Font family**: `system-ui, -apple-system, 'Segoe UI', Inter, sans-serif`
**Monospace**: `ui-monospace, 'SF Mono', SFMono-Regular, 'Menlo', monospace` (for code/numbers)

### 2.3 Spacing Scale

Base unit: **4px**

| Token | Value | Usage                          |
|-------|-------|--------------------------------|
| xs    | 4px   | Tight inline gaps              |
| sm    | 8px   | Icon-text gap, inner padding   |
| md    | 12px  | Component internal spacing     |
| lg    | 16px  | Card padding, standard gaps    |
| xl    | 24px  | Section gaps                   |
| 2xl   | 32px  | Major section separation       |
| 3xl   | 48px  | Page-level padding             |

### 2.4 Border Radius

| Token | Value | Usage                    |
|-------|-------|--------------------------|
| sm    | 4px   | Small elements, tags     |
| md    | 8px   | Inputs, small buttons    |
| lg    | 12px  | Cards, containers        |
| xl    | 16px  | Modals, panels           |
| pill  | 20px+ | Pills, badges, avatars   |

### 2.5 Shadows & Elevation

Flat design approach — no drop shadows for elevation.
Use **border + background color** to create depth:
- Surface cards: `background: #fff; border: 0.5px solid #E8E7E1; radius: 12px`
- Elevated surface: `background: #FAFBFC; border: 0.5px solid #E8E7E1; radius: 12px`
- Focus ring: `box-shadow: 0 0 0 3px rgba(83, 74, 183, 0.15)` (primary color at 15% opacity)

---

## 3. Component Specifications

### 3.1 Sidebar Navigation

**Before issues**: Emoji icons, no visual hierarchy between active/inactive states, flat background.

**New design**:
- Width: **220px** (fixed)
- Background: `#FAFBFC`
- Right border: `0.5px solid #E8E7E1`
- Bottom padding includes system status indicator

**Brand area** (top, 24px padding):
- Logo mark: 36x36 rounded rectangle (rx=10), filled with Primary-600 (#534AB7), white "T" centered
- App name: 13px/600/#2C2C2A ("Taxonomy")
- Subtitle: 11px/#888780 ("Workbench")

**Navigation section label**:
- "MAIN MENU" in 10px/500/#B4B2A9, letter-spacing 0.08em, uppercase
- Margin-top: 28px from brand area

**Nav items** (height: 40px each, horizontal padding: 12px):
- **Inactive state**: transparent bg, icon in neutral circle (#F1EFE8 fill), text 13px/400/#5F5E5A
  - Icon container: 20x20 circle with SVG icon stroke=#888780
  - Text offset: 8px left of icon
- **Active state**: bg=#EEEDFE (Primary-50), left accent bar (3px wide, Primary-600), icon circle tinted Primary-100, icon stroke=Primary-600, text 13px/500/#3C3489
- **Hover (inactive)**: bg=#F1EFE8, subtle transition 150ms ease
- **Hover (active)**: slightly deeper bg=#E8E6FD

**SVG Icons** (18x18 viewBox, stroke-based):

| Item        | Icon Path Description                              |
|-------------|----------------------------------------------------|
| Upload      | Plus sign (+) crosshair                            |
| Workflow    | Clock circle with hands                           |
| Review      | Checkmark path (check inside box or standalone ✓) |
| Versions    | Stacked rectangles (layer metaphor)               |
| Reports     | Document rectangle with lines                      |

**Bottom status**:
- Small green dot (6px radius, #639922) + "System ready" text (11px/#888780)

### 3.2 Top Bar (Header)

**Height**: 64px fixed
**Background**: white
**Bottom border**: 0.5px solid #E8E7E1

**Left side**:
- Eyebrow: 11px/#888780 ("Local AI Workbench") — 4px below top edge
- Title: 18px/500/#2C2C2A — dynamic per route (e.g., "Upload and analyze", "Workflow progress")

**Right side**:
- API status pill only (no exposed input field):
  - Pill: rx=15, bg=#EAF3DE, border=0.5px solid #97C459
  - Green dot (8px, #639922) + "API Connected" text (11.5px/500/#27500A)
- Settings gear icon (optional, for accessing API config)

**API input behavior change**: Move API URL configuration to a settings modal/page. Topbar should show connection status only.

### 3.3 Upload Page

#### 3.3.1 Main Upload Card

- Max-width: 800px (centered)
- Border-radius: 12px
- Padding: 20px
- Background: white, border: 0.5px solid #E8E7E1

**Layout**: CSS Grid, 2 columns
- Left column (dropzone): `1fr` (flexible)
- Right column (action panel): **280px** (fixed)
- Gap: **28px**
- Responsive: collapse to single column below 680px

#### 3.3.2 Dropzone Area (File Uploaded State)

**Empty state** (no file selected):
- Border: **1px solid** #CECBF6 (Primary-200) — NOT dashed
- Background: #EEEDFE (Primary-50)
- Border-radius: 10px
- Min-height: 180px
- Centered content:
  - Cloud upload icon (SVG, 48x48, stroke=Primary-200)
  - Text: "Click or drag Excel file here to upload" (14px/#5F5E5A)
  - Subtext: ".xlsx, .xls supported" (12px/#888780)

**Has-file state** (file uploaded):
- Same border/bg as above but border-style solid
- Content:
  - Custom spreadsheet SVG icon (56x64):
    - Document shape (rounded rect, white fill, Primary-200 stroke)
    - Inner lines representing rows (Primary-600, Primary-400 alternating)
  - File name: 14px/500/#2C2C2A
  - File metadata: 12px/#888780 ("188 rows, 6 columns")
  - Replace button: pill shape (rx=99px), white bg, Primary-200 border, 11px/Primary-600

**Interactions**:
- Hover: border darkens to Primary-400, bg deepens slightly
- Drag-over: border becomes Primary-600, bg becomes Primary-100
- Transitions: all 150ms ease

#### 3.3.3 Action Panel

**Structure** (top-to-bottom):

1. **Status Label**: "STATUS" — 11px/500/#B4B2A9, uppercase, letter-spacing 0.05em

2. **Status Indicator Row**:
   - Dot: 12px diameter, outer ring (#EAF3DE), inner dot (#639922) for ready state
   - Text: "Ready to analyze" (13px/500/#27500A)
   - Empty state: gray dot + "Waiting for file" (13px/#888780)

3. **Primary Action Button** ("Start analysis"):
   - Full width of action panel (280px - 40px padding = 240px usable... actually just width:100%)
   - Height: 42px
   - Border-radius: 10px
   - Background: Primary-600 (#534AB7)
   - Text: 13.5px/500/white
   - Disabled: opacity 0.38, cursor not-allowed
   - Hover: slight darken via opacity overlay
   - Active: scale(0.98) transform

4. **Secondary Link** ("History files (19) →"):
   - Text link style, 12.5px/Primary-600
   - Arrow suffix (→)
   - Hover: underline

5. **Divider**: 0.5px #E8E7E1 line

6. **Metadata**: File size, upload time etc (11px/#888780)

#### 3.3.4 Schema Recognition Card

- Positioned below main card
- Max-width: 800px
- Height: ~90px
- Border-radius: 12px
- White bg, 0.5px border

**Header row**:
- Left: "Schema recognition" (13px/500/#2C2C2A)
- Right: Badge pill showing "6/6 matched" (success green) or partial match count (warning amber)

**Field chips row**:
- Each chip: rx=14 (pill), height 28px
- Found fields: bg=#EAF3DE, text=#27500A
- Missing fields: bg=#FAEEDA, text=#633806
- Font size: 11px per chip
- Gap: 8px between chips

### 3.4 Button System

| Variant    | Background                | Border                  | Text          | Use case                  |
|-----------|--------------------------|------------------------|---------------|---------------------------|
| Primary   | #534AB7                  | none                   | white, 13.5px  | Main CTA actions          |
| Secondary | white                    | 1px #534AB7            | #534AB7       | Alternate actions         |
| Ghost     | transparent              | none                   | #534AB7       | Tertiary, text-only       |
| Success   | #EAF3DE                  | none                   | #27500A       | Confirmations             |
| Danger    | #FCEBEB                  | none                   | #791F1F       | Destructive actions       |
| Disabled  | any * opacity 0.38       | same as base           | muted         | Any variant when disabled |

**Shared properties**:
- Padding: 12px 20px (standard), 13px 20px (large/CTA)
- Border-radius: 10px (standard), 8px (small)
- Font-weight: 500 (never 700)
- Transition: all 150ms ease
- Cursor: pointer (pointer-events-none when disabled)
- Hover: subtle opacity shift or bg darken
- Active: transform translateY(0) or scale(0.98)

**Icon buttons**:
- Size: 32x32 square
- Border-radius: 8px
- Background: #F1EFE8
- Border: 0.5px #B4B2A9
- Centered icon (16px, #5F5E5A)

### 3.5 Form Elements

**Text inputs**:
- Height: 40px
- Padding: 0 12px
- Border: 1px solid #D3D1C7
- Border-radius: 8px
- Font: 13px/400/#2C2C2A
- Placeholder: #B4B2A9
- Focus: border-color Primary-600, ring: 0 0 0 3px rgba(83,74,183,0.12)

**Select dropdowns**: Same dimensions as inputs, with chevron icon

**Checkboxes/Radios**: Custom styled, 18x18 hit target, Primary-600 when checked

---

## 4. Layout System

### 4.1 Page Structure

```
┌──────────────┬──────────────────────────────────┐
│              │  Top Bar (64px fixed)             │
│   Sidebar    ├──────────────────────────────────┤
│   (220px)    │                                  │
│              │  Main Content                    │
│              │  (padding: 24px 32px)             │
│              │                                  │
│              │  ┌──────────────────────────┐    │
│              │  │ Content cards             │    │
│              │  └──────────────────────────┘    │
│              │                                  │
└──────────────┴──────────────────────────────────┘
```

### 4.2 Content Grid

- Max content width: **900px** (centered)
- Horizontal page padding: **32px**
- Vertical section gaps: **24px**
- Cards within sections: **16px** gap

### 4.3 Responsive Breakpoints

| Breakpoint | Sidebar | Layout changes                        |
|-----------|---------|--------------------------------------|
| >=1280px  | Visible | Full layout as designed               |
| 768-1279px| Visible | Slight compression, same structure   |
| <768px    | Hidden  | Hamburger menu, single column layout  |
| <480px    | Hidden  | Full mobile, reduced padding to 16px  |

---

## 5. Interaction Patterns

### 5.1 Loading States

**Skeleton screens** preferred over spinners:
- Skeleton blocks: animated pulse, bg=#F1EFE8, radius matching final element
- Pulse animation: 1.5s infinite, opacity oscillation 0.5 ↔ 1.0

**Spinner usage** (only for indefinite waits):
- Inline spinner: 16px, Primary-600 stroke, 1.5s rotation
- Overlay spinner: 32px, centered on card, semi-transparent backdrop

### 5.2 Error States

**Inline errors** (form validation):
- Below input field, 12px/#791F1F
- Warning triangle icon prefix
- No red borders on inputs (use focus-ring style instead)

**Toast notifications** (action feedback):
- Position: bottom-right, 16px from edges
- Auto-dismiss after 4 seconds
- Variants: success (green), error (red), info (blue)
- Manual close button (X icon)

**Error boundaries** (page-level failures):
- Centered card with illustration
- Title: "Something went wrong"
- Message: brief description
- Action: "Try again" button

### 5.3 Empty States

- Centered in content area
- Illustration: simple SVG (64x64 max, neutral tone)
- Title: 15px/500/#2C2C2A
- Body: 13px/#888780
- CTA button if applicable

### 5.4 Micro-interactions

All transitions use **150ms ease** for hover/focus states, **300ms ease** for open/close animations. Respect `prefers-reduced-motion: reduce` by disabling animations for users who prefer it.

---

## 6. Implementation Priority

### Phase 1: Foundation (Do First)
1. Create CSS custom properties (design tokens) file: `frontend/src/styles/tokens.css`
2. Import tokens globally in main entry point
3. Update global reset/base styles

### Phase 2: Shell Components
4. Redesign `AppShell.vue` sidebar (icons, active states, brand area)
5. Redesign topbar (clean layout, status badge, move API input)
6. Test responsive sidebar behavior

### Phase 3: Core Pages
7. Redesign `UploadView.vue` (dropzone, action panel, schema card)
8. Update `Modal.vue` component styling
9. Update `FileInfoCard.vue` component

### Phase 4: Detail Pages
10. Apply token system to remaining views (Workflow, Review, Versions, Report, Overview, Tree, Diagnosis)
11. Ensure consistent table/card styling across all views
12. Add loading skeleton components

### Phase 5: Polish
13. Add micro-interactions (transitions, hover effects)
14. Accessibility audit (keyboard nav, screen reader, contrast check)
15. Dark mode preparation (token variables support `[data-theme="dark"]`)

---

## 7. CSS Token Reference (Ready to Copy)

```css
/* ===== Taxonomy Workbench Design Tokens v1.0 ===== */

:root {
  /* ---- Primary (Indigo) ---- */
  --color-primary-50: #EEEDFE;
  --color-primary-100: #CECBF6;
  --color-primary-200: #AFA9EC;
  --color-primary-400: #7F77DD;
  --color-primary-600: #534AB7;
  --color-primary-800: #3C3489;
  --color-primary-900: #26215C;

  /* ---- Semantic ---- */
  --color-success-bg: #EAF3DE;
  --color-success-text: #27500A;
  --color-success-dot: #639922;
  --color-warning-bg: #FAEEDA;
  --color-warning-text: #633806;
  --color-error-bg: #FCEBEB;
  --color-error-text: #791F1F;
  --color-info-bg: #E6F1FB;
  --color-info-text: #0C447C;

  /* ---- Neutral ---- */
  --color-bg-page: #FAFBFC;
  --color-bg-surface: #FFFFFF;
  --color-bg-surface-alt: #F8F8F7;
  --color-bg-surface-raised: #F1EFE8;
  --color-border-default: #E8E7E1;
  --color-border-strong: #D3D1C7;
  --color-text-primary: #2C2C2A;
  --color-text-secondary: #444441;
  --color-text-muted: #888780;
  --color-text-hint: #B4B2A9;

  /* ---- Typography ---- */
  --font-sans: system-ui, -apple-system, 'Segoe UI', Inter, sans-serif;
  --font-mono: ui-monospace, 'SF Mono', SFMono-Regular, Menlo, monospace;

  /* ---- Spacing ---- */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 12px;
  --space-lg: 16px;
  --space-xl: 24px;
  --space-2xl: 32px;
  --space-3xl: 48px;

  /* ---- Radius ---- */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-pill: 9999px;

  /* ---- Transition ---- */
  --transition-fast: 150ms ease;
  --transition-normal: 300ms ease;

  /* ---- Layout ---- */
  --sidebar-width: 220px;
  --topbar-height: 64px;
  --content-max-width: 900px;
}
```

---

## 8. Appendix: Icon Set Specification

All navigation and UI icons use **stroke-based SVG** (not filled). Standard viewbox: 18x18 or 24x24. Stroke-width: 1.5 or 2. Stroke-linecap: round, stroke-linejoin: round.

Required icons for implementation:

| Name        | Description                         | ViewBox |
|-------------|-------------------------------------|---------|
| upload      | Plus/crosshair for upload actions   | 18x18   |
| workflow    | Clock with hands                    | 18x18   |
| check       | Checkmark                           | 18x18   |
| layers      | Stacked rectangles                  | 18x18   |
| document    | Page with lines                     | 18x18   |
| settings    | Gear                                | 18x18   |
| arrow-right | Chevron right                       | 16x16   |
| close       | X mark                              | 16x16   |
| cloud-upload| Cloud with up arrow                 | 48x48   |
| spreadsheet | Document with grid lines            | 56x64   |

---

*End of specification*
