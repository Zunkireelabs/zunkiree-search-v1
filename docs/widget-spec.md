# Zunkiree Search v1 - Widget Specification

## Overview

The Zunkiree Widget is a lightweight, embeddable search interface that allows website visitors to ask natural language questions and receive AI-powered answers based on the business's data.

---

## Embed Code

```html
<script
  src="https://cdn.zunkiree.ai/widget/v1/search.js"
  data-site-id="YOUR_SITE_ID"
  async
></script>
```

### Attributes

| Attribute | Required | Description |
|-----------|----------|-------------|
| `data-site-id` | Yes | Unique identifier for the customer |
| `data-position` | No | Widget position: `bottom-right` (default), `bottom-left` |
| `data-theme` | No | Theme: `light` (default), `dark`, `auto` |

---

## Widget States

### 1. Closed State
- Floating action button in corner
- Shows brand icon or search icon
- Subtle hover effect

### 2. Open State
- Expanded chat container
- Header with brand name and close button
- Message area
- Input field with send button

### 3. Loading State
- Typing indicator (three dots animation)
- Input disabled during response

### 4. Error State
- Friendly error message
- Retry option

---

## UI Components

### Trigger Button
```
┌─────────────────────┐
│                     │
│    [Search Icon]    │  ← Floating button
│                     │
└─────────────────────┘
```

### Chat Container (Open)
```
┌─────────────────────────────────────┐
│  [Brand Name]              [X]      │  ← Header
├─────────────────────────────────────┤
│                                     │
│  Welcome! How can I help you today? │  ← Welcome message
│                                     │
│  ┌─────────────────────────────┐   │
│  │ What are your services?     │   │  ← User message
│  └─────────────────────────────┘   │
│                                     │
│  ┌─────────────────────────────┐   │
│  │ We offer the following...   │   │  ← Assistant message
│  │                             │   │
│  │ [Suggestion 1] [Suggest 2]  │   │  ← Follow-ups
│  └─────────────────────────────┘   │
│                                     │
├─────────────────────────────────────┤
│  [Ask a question...        ] [>]    │  ← Input area
└─────────────────────────────────────┘
```

---

## Styling

### Default Theme
```css
:root {
  --zk-primary: #2563eb;
  --zk-background: #ffffff;
  --zk-text: #1f2937;
  --zk-text-secondary: #6b7280;
  --zk-border: #e5e7eb;
  --zk-user-bubble: #2563eb;
  --zk-user-text: #ffffff;
  --zk-assistant-bubble: #f3f4f6;
  --zk-assistant-text: #1f2937;
  --zk-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  --zk-radius: 12px;
  --zk-font: system-ui, -apple-system, sans-serif;
}
```

### Dimensions
| Element | Size |
|---------|------|
| Trigger button | 56px x 56px |
| Chat container | 380px x 520px (desktop) |
| Chat container (mobile) | 100% x 100% |
| Input field height | 48px |
| Message max-width | 80% |

### Responsive Breakpoints
- Desktop: > 640px
- Mobile: <= 640px (full-screen mode)

---

## Behavior

### Initialization
1. Script loads asynchronously
2. Fetch widget config from API
3. Apply brand colors and settings
4. Render trigger button
5. Wait for user interaction

### User Interaction Flow
1. User clicks trigger button
2. Chat container opens with animation
3. Welcome message displayed
4. User types question and presses Enter or clicks send
5. Input disabled, loading indicator shown
6. API request sent
7. Response received and rendered
8. Follow-up suggestions shown (if enabled)
9. Input re-enabled

### Keyboard Navigation
| Key | Action |
|-----|--------|
| Enter | Send message |
| Escape | Close widget |
| Tab | Navigate between elements |

---

## API Integration

### Get Config
```javascript
// On init
fetch(`${API_BASE}/widget/config/${siteId}`)
  .then(res => res.json())
  .then(config => {
    applyTheme(config.primary_color);
    setWelcomeMessage(config.welcome_message);
    setPlaceholder(config.placeholder_text);
  });
```

### Send Query
```javascript
// On submit
fetch(`${API_BASE}/query`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    site_id: siteId,
    question: userInput
  })
})
  .then(res => res.json())
  .then(data => {
    renderMessage('assistant', data.answer);
    if (data.suggestions) {
      renderSuggestions(data.suggestions);
    }
  });
```

---

## Accessibility

### Requirements
- WCAG 2.1 AA compliant
- Keyboard navigable
- Screen reader compatible
- Focus management
- Sufficient color contrast

### ARIA Labels
```html
<button aria-label="Open search assistant">
<div role="dialog" aria-label="Search assistant">
<div role="log" aria-live="polite">
<input aria-label="Type your question">
```

---

## Performance

### Targets
| Metric | Target |
|--------|--------|
| Bundle size (gzipped) | < 30KB |
| Time to interactive | < 500ms |
| First response | < 2s |

### Optimizations
- Lazy load on trigger hover
- Minimal dependencies
- CSS-in-JS (no external stylesheets)
- Efficient DOM updates

---

## Build Output

### Files
```
dist/
├── search.js          # Main bundle (IIFE)
├── search.js.map      # Source map
└── search.min.js      # Minified production bundle
```

### Bundle Format
```javascript
(function() {
  'use strict';

  // Widget code here

  // Auto-initialize
  const script = document.currentScript;
  const siteId = script.getAttribute('data-site-id');

  if (siteId) {
    window.ZunkireeWidget.init({ siteId });
  }
})();
```

---

## Configuration Options (Future)

```html
<script
  src="https://cdn.zunkiree.ai/widget/v1/search.js"
  data-site-id="admizz"
  data-position="bottom-right"
  data-theme="light"
  data-language="en"
  data-auto-open="false"
  data-open-delay="5000"
></script>
```

---

## Testing Checklist

- [ ] Widget loads on various websites
- [ ] Correct branding applied
- [ ] Questions submitted successfully
- [ ] Responses rendered correctly
- [ ] Follow-up suggestions work
- [ ] Mobile responsive
- [ ] Keyboard navigation
- [ ] Cross-browser (Chrome, Firefox, Safari, Edge)
- [ ] No console errors
- [ ] No style conflicts with host page
