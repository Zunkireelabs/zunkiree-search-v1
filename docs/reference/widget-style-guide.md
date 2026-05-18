# Zunkiree Search Widget - Style Guide

> Version: 2.0 (Search-First Design)
> Last Updated: December 26, 2024
> Status: Design Specification

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Embed Modes](#embed-modes)
3. [Component Architecture](#component-architecture)
4. [Design Tokens](#design-tokens)
5. [Component Specifications](#component-specifications)
6. [States & Interactions](#states--interactions)
7. [Responsive Design](#responsive-design)
8. [Animation Guidelines](#animation-guidelines)
9. [Accessibility](#accessibility)
10. [Implementation Notes](#implementation-notes)
11. [Embed Code Examples](#embed-code-examples)

---

## Design Philosophy

### Core Principles

| Principle | Description |
|-----------|-------------|
| **Search-First** | The search bar is the hero, not hidden in a corner |
| **Core Feature** | Feels like part of the site, not an add-on chatbot |
| **Instant Ready** | Always visible, ready to use immediately |
| **Clean & Minimal** | No chat bubbles, no chatbot personality |
| **Future-Ready** | Structured for Generative UI capabilities |

### Before vs After

```
BEFORE (v1 - Chatbot Style)          AFTER (v2 - Search First)
─────────────────────────────        ─────────────────────────────

┌─────────────────────┐              ┌─────────────────────────────┐
│                     │              │                             │
│   Website Content   │              │   ┌─────────────────────┐   │
│                     │              │   │ 🔍 Ask anything...  │   │
│                     │              │   └─────────────────────┘   │
│           ┌───────┐ │              │     Powered by Zunkiree AI  │
│           │ Chat  │ │              │                             │
│           │  💬   │ │              │   Website Content           │
│           └───────┘ │              │                             │
└─────────────────────┘              └─────────────────────────────┘

❌ Hidden trigger button              ✅ Prominent search bar
❌ Opens in floating panel            ✅ Embedded in page
❌ Chat bubble UI                     ✅ Search results UI
```

---

## Embed Modes

### Mode 1: Hero

Full-width search bar, typically placed in hero sections.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│                   What would you like to know?                      │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │  🔍   Ask anything about our services...              Search│  │
│   └─────────────────────────────────────────────────────────────┘  │
│                      ✨ Powered by Zunkiree AI                      │
│                                                                     │
│       [ Pricing ]    [ Services ]    [ Contact ]    [ Hours ]      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Specifications:**
- Width: 100% of container (max-width: 640px centered)
- Search bar height: 56px
- Border radius: 12px or 9999px (pill)
- Shadow: Prominent (elevation-md)

---

### Mode 2: Inline

Compact search bar for embedding within content sections.

```
┌───────────────────────────────────────────────────────────────┐
│  🔍  Search our knowledge base...                      Search │
│      ✨ Powered by Zunkiree AI                                │
└───────────────────────────────────────────────────────────────┘
```

**Specifications:**
- Width: Flexible (100% of parent, or set max-width)
- Search bar height: 48px
- Border radius: 8px
- Shadow: Subtle (elevation-sm)

---

### Mode 3: Floating

Minimal floating search (optional fallback for legacy support).

```
                                    ┌─────────────────────────┐
                                    │ 🔍 Ask anything...      │
                                    └─────────────────────────┘
```

**Specifications:**
- Position: Fixed, bottom-right (20px offset)
- Width: 320px
- Search bar height: 44px
- Border radius: 9999px (pill)
- Shadow: elevation-lg

---

## Component Architecture

### Component Tree

```
ZunkireeSearch (Root)
│
├── SearchBar
│   ├── SearchIcon
│   ├── InputField
│   ├── ClearButton (when has input)
│   └── SubmitButton
│
├── PoweredByBadge
│
├── QuickActions (optional)
│   └── ActionChip[]
│
├── ResultsPanel (appears on search)
│   ├── ResultCard
│   │   ├── AnswerContent
│   │   ├── SourcesList
│   │   │   └── SourceLink[]
│   │   └── FollowUpActions
│   │       └── SuggestionChip[]
│   │
│   └── ConversationHistory (collapsible)
│       └── MessageItem[]
│
└── LoadingState
    └── SkeletonLoader
```

### File Structure

```
widget/
├── src/
│   ├── main.tsx
│   ├── components/
│   │   ├── ZunkireeSearch.tsx      # Root component
│   │   ├── SearchBar.tsx           # Search input
│   │   ├── ResultsPanel.tsx        # Results container
│   │   ├── ResultCard.tsx          # Individual result
│   │   ├── QuickActions.tsx        # Suggestion chips
│   │   ├── SourceLink.tsx          # Source attribution
│   │   ├── PoweredBy.tsx           # Branding badge
│   │   └── LoadingState.tsx        # Loading skeleton
│   ├── styles/
│   │   ├── tokens.ts               # Design tokens
│   │   ├── components/
│   │   │   ├── searchBar.ts
│   │   │   ├── results.ts
│   │   │   ├── chips.ts
│   │   │   └── loading.ts
│   │   └── index.ts                # Style aggregator
│   ├── hooks/
│   │   ├── useSearch.ts            # Search logic
│   │   └── useConfig.ts            # Config fetching
│   └── types/
│       └── index.ts                # TypeScript types
└── dist/
    └── zunkiree-search.iife.js
```

---

## Design Tokens

### Colors

```typescript
// tokens.ts

export const colors = {
  // Primary (from config - these are defaults)
  primary: {
    DEFAULT: '#2563EB',           // Blue-600
    hover: '#1D4ED8',             // Blue-700
    light: 'rgba(37, 99, 235, 0.1)',
    text: '#FFFFFF',
  },

  // Neutrals
  background: '#FFFFFF',
  surface: '#F9FAFB',             // Gray-50
  surfaceHover: '#F3F4F6',        // Gray-100

  // Borders
  border: {
    DEFAULT: '#E5E7EB',           // Gray-200
    focus: '#2563EB',             // Primary
    hover: '#D1D5DB',             // Gray-300
  },

  // Text
  text: {
    primary: '#111827',           // Gray-900
    secondary: '#6B7280',         // Gray-500
    muted: '#9CA3AF',             // Gray-400
    inverse: '#FFFFFF',
  },

  // Semantic
  success: '#10B981',             // Emerald-500
  error: '#EF4444',               // Red-500
  warning: '#F59E0B',             // Amber-500
};
```

### Typography

```typescript
export const typography = {
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",

  // Font Sizes
  fontSize: {
    xs: '12px',
    sm: '13px',
    base: '15px',
    lg: '16px',
    xl: '18px',
    '2xl': '24px',
  },

  // Font Weights
  fontWeight: {
    normal: '400',
    medium: '500',
    semibold: '600',
  },

  // Line Heights
  lineHeight: {
    tight: '1.25',
    normal: '1.5',
    relaxed: '1.625',
  },

  // Specific Styles
  styles: {
    searchInput: {
      fontSize: '16px',
      fontWeight: '400',
      lineHeight: '1.5',
    },
    placeholder: {
      fontSize: '16px',
      fontWeight: '400',
      color: '#9CA3AF',
    },
    resultText: {
      fontSize: '15px',
      fontWeight: '400',
      lineHeight: '1.625',
      color: '#111827',
    },
    sourceLink: {
      fontSize: '13px',
      fontWeight: '500',
      color: '#6B7280',
    },
    poweredBy: {
      fontSize: '12px',
      fontWeight: '400',
      color: '#9CA3AF',
    },
    chipText: {
      fontSize: '14px',
      fontWeight: '500',
    },
  },
};
```

### Spacing

```typescript
export const spacing = {
  // Base units
  px: '1px',
  0: '0',
  1: '4px',
  2: '8px',
  3: '12px',
  4: '16px',
  5: '20px',
  6: '24px',
  8: '32px',
  10: '40px',
  12: '48px',

  // Component-specific
  container: {
    padding: '24px',
    paddingMobile: '16px',
  },
  searchBar: {
    paddingX: '16px',
    paddingY: '14px',
    height: {
      hero: '56px',
      inline: '48px',
      floating: '44px',
    },
  },
  resultCard: {
    padding: '20px',
    gap: '16px',
  },
  chip: {
    paddingX: '12px',
    paddingY: '6px',
    gap: '8px',
  },
};
```

### Border Radius

```typescript
export const borderRadius = {
  none: '0',
  sm: '4px',
  DEFAULT: '6px',
  md: '8px',
  lg: '12px',
  xl: '16px',
  full: '9999px',

  // Component-specific
  searchBar: {
    rounded: '12px',
    pill: '9999px',
  },
  resultCard: '8px',
  chip: '6px',
  source: '6px',
};
```

### Shadows

```typescript
export const shadows = {
  none: 'none',
  sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
  DEFAULT: '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)',
  md: '0 4px 6px rgba(0, 0, 0, 0.1), 0 2px 4px rgba(0, 0, 0, 0.06)',
  lg: '0 10px 15px rgba(0, 0, 0, 0.1), 0 4px 6px rgba(0, 0, 0, 0.05)',
  xl: '0 20px 25px rgba(0, 0, 0, 0.1), 0 10px 10px rgba(0, 0, 0, 0.04)',

  // Component-specific
  searchBar: {
    default: '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)',
    focus: '0 4px 6px rgba(0, 0, 0, 0.1), 0 2px 4px rgba(0, 0, 0, 0.06)',
    hover: '0 4px 6px rgba(0, 0, 0, 0.07), 0 2px 4px rgba(0, 0, 0, 0.04)',
  },
  resultsPanel: '0 10px 25px rgba(0, 0, 0, 0.1), 0 6px 10px rgba(0, 0, 0, 0.05)',
};
```

### Transitions

```typescript
export const transitions = {
  duration: {
    fast: '100ms',
    DEFAULT: '150ms',
    slow: '200ms',
    slower: '300ms',
  },
  timing: {
    DEFAULT: 'ease-in-out',
    in: 'ease-in',
    out: 'ease-out',
    bounce: 'cubic-bezier(0.68, -0.55, 0.265, 1.55)',
  },

  // Presets
  default: '150ms ease-in-out',
  fast: '100ms ease-in-out',
  slow: '200ms ease-out',

  // Properties
  properties: {
    all: 'all',
    colors: 'background-color, border-color, color, fill, stroke',
    opacity: 'opacity',
    shadow: 'box-shadow',
    transform: 'transform',
  },
};
```

### Z-Index

```typescript
export const zIndex = {
  base: '1',
  dropdown: '1000',
  sticky: '1100',
  fixed: '1200',
  modalBackdrop: '1300',
  modal: '1400',
  popover: '1500',
  tooltip: '1600',

  // Widget-specific
  widget: '9999',
  resultsPanel: '10000',
};
```

---

## Component Specifications

### SearchBar

```
┌─────────────────────────────────────────────────────────────────────┐
│  🔍   What would you like to know?                          Search │
└─────────────────────────────────────────────────────────────────────┘
   │         │                                                   │
   │         │                                                   │
   │         └── Input Field                                     │
   │             • Placeholder: config.placeholder_text          │
   │             • Font: 16px, regular                          │
   │             • No border (container has border)             │
   │                                                             │
   └── Search Icon                                               │
       • Size: 20x20px                                           │
       • Color: text.muted                                       │
       • Margin-right: 12px                                      │
                                                                 │
                                              Submit Button ─────┘
                                              • Text: "Search" or Icon
                                              • Background: primary
                                              • Padding: 12px 20px
                                              • Border-radius: 8px
```

**CSS Structure:**

```css
.zk-search-bar {
  display: flex;
  align-items: center;
  width: 100%;
  height: 56px;                           /* hero mode */
  padding: 0 8px 0 16px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  transition: all 150ms ease-in-out;
}

.zk-search-bar:hover {
  border-color: #D1D5DB;
  box-shadow: 0 4px 6px rgba(0,0,0,0.07);
}

.zk-search-bar:focus-within {
  border-color: var(--zk-primary);
  box-shadow: 0 4px 6px rgba(0,0,0,0.1), 0 0 0 3px var(--zk-primary-light);
}

.zk-search-icon {
  width: 20px;
  height: 20px;
  color: #9CA3AF;
  flex-shrink: 0;
  margin-right: 12px;
}

.zk-search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 16px;
  color: #111827;
  background: transparent;
}

.zk-search-input::placeholder {
  color: #9CA3AF;
}

.zk-search-button {
  padding: 10px 20px;
  background: var(--zk-primary);
  color: #FFFFFF;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: background 150ms ease-in-out;
}

.zk-search-button:hover {
  background: var(--zk-primary-hover);
}
```

---

### ResultsPanel

```
╔═════════════════════════════════════════════════════════════════════╗
║                                                                     ║
║  Sofa cleaning starts at $50 for a standard 3-seater sofa.         ║
║  For heavily stained sofas or larger sectionals, prices            ║
║  range from $75-$150 depending on size and condition.              ║
║                                                                     ║
║  ┌─────────────────────────────────────────────────────────────┐   ║
║  │ 📄 Source: Pricing Page  →                                  │   ║
║  └─────────────────────────────────────────────────────────────┘   ║
║                                                                     ║
║  [ How long does it take? ]  [ Book now ]  [ Other services ]      ║
║                                                                     ║
╚═════════════════════════════════════════════════════════════════════╝
```

**CSS Structure:**

```css
.zk-results-panel {
  margin-top: 8px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.1);
  overflow: hidden;
  animation: zk-fade-in 200ms ease-out;
}

.zk-result-card {
  padding: 20px;
}

.zk-result-content {
  font-size: 15px;
  line-height: 1.625;
  color: #111827;
  margin-bottom: 16px;
}

.zk-source-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #F9FAFB;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #6B7280;
  text-decoration: none;
  transition: background 150ms ease-in-out;
}

.zk-source-link:hover {
  background: #F3F4F6;
  color: #111827;
}

.zk-follow-up-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #E5E7EB;
}
```

---

### QuickActions / Chips

```
    [ Pricing ]    [ Services ]    [ Contact ]    [ Hours ]
        │
        └── Chip Component
            • Background: transparent (or surface on hover)
            • Border: 1px solid border.DEFAULT
            • Padding: 6px 12px
            • Font: 14px, medium weight
            • Border-radius: 6px
```

**CSS Structure:**

```css
.zk-quick-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 16px;
}

.zk-chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  background: transparent;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  color: #6B7280;
  cursor: pointer;
  transition: all 150ms ease-in-out;
}

.zk-chip:hover {
  background: #F9FAFB;
  border-color: #D1D5DB;
  color: #111827;
}

.zk-chip:active {
  background: #F3F4F6;
}

/* Primary variant (for "Search" or primary actions) */
.zk-chip--primary {
  background: var(--zk-primary);
  border-color: var(--zk-primary);
  color: #FFFFFF;
}

.zk-chip--primary:hover {
  background: var(--zk-primary-hover);
  border-color: var(--zk-primary-hover);
  color: #FFFFFF;
}
```

---

### PoweredBy Badge

```
    ✨ Powered by Zunkiree AI
       │
       └── Badge Component
           • Font: 12px, regular
           • Color: text.muted
           • Centered below search bar
           • Margin-top: 12px
```

**CSS Structure:**

```css
.zk-powered-by {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 12px;
  font-size: 12px;
  color: #9CA3AF;
}

.zk-powered-by__icon {
  font-size: 14px;
}

.zk-powered-by__link {
  color: var(--zk-primary);
  text-decoration: none;
  font-weight: 500;
}

.zk-powered-by__link:hover {
  text-decoration: underline;
}
```

---

### LoadingState

```
╔═════════════════════════════════════════════════════════════════════╗
║                                                                     ║
║     ████████████████░░░░░░░░░░░░░░░░░░░░░░░░                       ║
║     ████████████████████████████░░░░░░░░░░░░                       ║
║     ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░                       ║
║                                                                     ║
╚═════════════════════════════════════════════════════════════════════╝
```

**CSS Structure:**

```css
.zk-loading {
  padding: 20px;
}

.zk-skeleton {
  background: linear-gradient(90deg, #F3F4F6 25%, #E5E7EB 50%, #F3F4F6 75%);
  background-size: 200% 100%;
  animation: zk-shimmer 1.5s infinite;
  border-radius: 4px;
}

.zk-skeleton--line {
  height: 16px;
  margin-bottom: 12px;
}

.zk-skeleton--line:nth-child(1) { width: 90%; }
.zk-skeleton--line:nth-child(2) { width: 75%; }
.zk-skeleton--line:nth-child(3) { width: 60%; }

@keyframes zk-shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
```

---

## States & Interactions

### Search Bar States

| State | Visual Changes |
|-------|----------------|
| **Default** | Border: #E5E7EB, Shadow: sm |
| **Hover** | Border: #D1D5DB, Shadow: md |
| **Focus** | Border: primary, Shadow: md + ring |
| **Loading** | Input disabled, spinner in button |
| **Error** | Border: error, Error message below |

### Results Panel States

| State | Behavior |
|-------|----------|
| **Hidden** | Not rendered (display: none) |
| **Loading** | Show skeleton loader |
| **Results** | Fade in with animation |
| **Error** | Show error message with retry |
| **No Results** | Show helpful message |

### Interaction Flow

```
User Types Query
       │
       ▼
┌──────────────────┐
│  Show Dropdown   │ (optional: autocomplete)
│  Suggestions     │
└──────────────────┘
       │
       ▼ (Enter or Click Search)
┌──────────────────┐
│  Loading State   │
│  (Skeleton)      │
└──────────────────┘
       │
       ▼
┌──────────────────┐
│  Results Panel   │
│  Expands Below   │
└──────────────────┘
       │
       ▼ (Click Follow-up)
┌──────────────────┐
│  New Query       │
│  (Repeat)        │
└──────────────────┘
```

---

## Responsive Design

### Breakpoints

```typescript
export const breakpoints = {
  sm: '640px',   // Mobile landscape
  md: '768px',   // Tablet
  lg: '1024px',  // Desktop
  xl: '1280px',  // Large desktop
};
```

### Mobile Adaptations (< 640px)

```css
@media (max-width: 639px) {
  .zk-container {
    padding: 16px;
  }

  .zk-search-bar {
    height: 48px;
    border-radius: 8px;
  }

  .zk-search-button {
    padding: 8px 16px;
    font-size: 14px;
  }

  /* Or icon-only button on mobile */
  .zk-search-button__text {
    display: none;
  }

  .zk-results-panel {
    border-radius: 8px;
  }

  .zk-quick-actions {
    justify-content: flex-start;
    overflow-x: auto;
    flex-wrap: nowrap;
    padding-bottom: 8px;
  }

  .zk-chip {
    flex-shrink: 0;
  }
}
```

### Touch Considerations

- Minimum tap target: 44x44px
- Increased spacing on mobile
- Larger touch areas for chips
- Swipe-to-dismiss for results (optional)

---

## Animation Guidelines

### Core Animations

```css
/* Fade In - Results Panel */
@keyframes zk-fade-in {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Shimmer - Loading Skeleton */
@keyframes zk-shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}

/* Pulse - Loading Indicator */
@keyframes zk-pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

/* Spin - Loading Spinner */
@keyframes zk-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
```

### Animation Usage

| Animation | Duration | Easing | Use Case |
|-----------|----------|--------|----------|
| Fade In | 200ms | ease-out | Results appear |
| Shimmer | 1.5s | linear | Loading skeleton |
| Hover transitions | 150ms | ease-in-out | Buttons, chips |
| Focus ring | 150ms | ease-in-out | Search bar focus |

### Performance Rules

1. Use `transform` and `opacity` only (GPU accelerated)
2. Avoid animating `width`, `height`, `top`, `left`
3. Use `will-change` sparingly
4. Respect `prefers-reduced-motion`

```css
@media (prefers-reduced-motion: reduce) {
  .zk-results-panel {
    animation: none;
  }

  .zk-skeleton {
    animation: none;
    background: #F3F4F6;
  }
}
```

---

## Accessibility

### ARIA Attributes

```html
<!-- Search Bar -->
<div role="search" class="zk-search-bar">
  <label for="zk-search-input" class="sr-only">Search</label>
  <input
    id="zk-search-input"
    type="search"
    role="searchbox"
    aria-label="Search"
    aria-describedby="zk-powered-by"
    autocomplete="off"
  />
  <button type="submit" aria-label="Submit search">
    Search
  </button>
</div>

<!-- Results -->
<div
  role="region"
  aria-label="Search results"
  aria-live="polite"
  aria-busy="false"
>
  <!-- Results content -->
</div>

<!-- Loading State -->
<div role="status" aria-live="polite">
  <span class="sr-only">Loading results...</span>
</div>
```

### Keyboard Navigation

| Key | Action |
|-----|--------|
| `Tab` | Move between interactive elements |
| `Enter` | Submit search / Activate button |
| `Escape` | Clear input / Close results |
| `Arrow Down` | Navigate suggestions (if autocomplete) |
| `Arrow Up` | Navigate suggestions (if autocomplete) |

### Focus Management

```css
/* Visible focus ring */
.zk-search-bar:focus-within {
  outline: none;
  box-shadow: 0 0 0 3px var(--zk-primary-light);
}

/* Focus visible for keyboard users */
.zk-chip:focus-visible,
.zk-search-button:focus-visible {
  outline: 2px solid var(--zk-primary);
  outline-offset: 2px;
}
```

### Screen Reader Only Class

```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

---

## Implementation Notes

### CSS Class Naming Convention

All classes prefixed with `zk-` to avoid conflicts:

```
.zk-                    # Namespace prefix
.zk-search-bar          # Component
.zk-search-bar--hero    # Modifier (mode)
.zk-search-bar__input   # Element (BEM-style)
.zk-search-bar--loading # State modifier
```

### CSS Custom Properties (Runtime Theming)

```css
:root {
  --zk-primary: #2563EB;
  --zk-primary-hover: #1D4ED8;
  --zk-primary-light: rgba(37, 99, 235, 0.1);
}
```

Applied at runtime from config:

```typescript
const applyTheme = (primaryColor: string) => {
  document.documentElement.style.setProperty('--zk-primary', primaryColor);
  document.documentElement.style.setProperty('--zk-primary-hover', darken(primaryColor, 10));
  document.documentElement.style.setProperty('--zk-primary-light', alpha(primaryColor, 0.1));
};
```

### Bundle Size Targets

| Metric | Target |
|--------|--------|
| JS Bundle (gzipped) | < 50KB |
| Total Size | < 60KB |
| Initial Paint | < 100ms |
| Interactive | < 200ms |

---

## Embed Code Examples

### Hero Mode (Recommended)

```html
<!-- In your hero section -->
<div class="your-hero-section">
  <h1>Welcome to Our Site</h1>

  <!-- Zunkiree Search -->
  <div id="zunkiree-search"></div>
  <script
    src="https://cdn.zunkiree.ai/v2/search.js"
    data-site-id="your-site-id"
    data-mode="hero"
    data-placeholder="What can we help you find?"
  ></script>
</div>
```

### Inline Mode

```html
<!-- In your FAQ or help section -->
<div class="faq-section">
  <h2>Frequently Asked Questions</h2>

  <div id="zunkiree-search" style="max-width: 600px; margin: 0 auto;"></div>
  <script
    src="https://cdn.zunkiree.ai/v2/search.js"
    data-site-id="your-site-id"
    data-mode="inline"
  ></script>
</div>
```

### Floating Mode (Legacy)

```html
<!-- Just before </body> -->
<script
  src="https://cdn.zunkiree.ai/v2/search.js"
  data-site-id="your-site-id"
  data-mode="floating"
></script>
```

### Full Configuration

```html
<div id="zunkiree-search"></div>
<script
  src="https://cdn.zunkiree.ai/v2/search.js"
  data-site-id="your-site-id"
  data-api-url="https://api.zunkiree.ai"
  data-mode="hero"
  data-placeholder="Ask anything..."
  data-show-powered-by="true"
  data-show-quick-actions="true"
  data-border-radius="pill"
></script>
```

---

## Configuration Interface

```typescript
interface ZunkireeConfig {
  // Required
  siteId: string;

  // API
  apiUrl?: string;                    // Default: https://api.zunkiree.ai

  // Display Mode
  mode?: 'hero' | 'inline' | 'floating';  // Default: hero

  // Appearance (from backend config)
  brandName?: string;
  primaryColor?: string;              // Default: #2563EB
  placeholderText?: string;           // Default: "What would you like to know?"

  // Features
  showPoweredBy?: boolean;            // Default: true
  showQuickActions?: boolean;         // Default: true
  quickActions?: string[];            // Default: from backend
  showSources?: boolean;              // Default: true

  // Style
  borderRadius?: 'rounded' | 'pill';  // Default: rounded

  // Callbacks (for advanced integration)
  onSearch?: (query: string) => void;
  onResult?: (result: SearchResult) => void;
  onError?: (error: Error) => void;
}
```

---

## Changelog

### v2.0.0 (December 2024)
- Complete redesign from chatbot to search-first
- Added 3 embed modes: Hero, Inline, Floating
- New component architecture
- Design tokens system
- Accessibility improvements
- Reduced bundle size

### v1.0.0 (December 2024)
- Initial release (chatbot style)

---

*This style guide should be updated as the design evolves.*
