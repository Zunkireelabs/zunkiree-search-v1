# Generative UI — Design Guideline (education)

How the counselor's cards look, behave and read. Pairs with the [card catalog](./generative-ui-card-catalog.md).

Styles live in one file: `widget/src/components/blocks/blockStyles.ts`. All classes start with `zk-` so they never clash with the host website.
The older `widget-style-guide.md` covers the base widget (search bar, panels), not these cards.

---

## 1. Principles

1. **One card type always looks the same.** The widget owns the look. The backend and the LLM only send data.
2. **Facts come from code, not the LLM.** Card data, titles, intro sentences and buttons are all built by code from real tenant data.
3. **Never offer what we can't deliver.** No button, tile or option leads to a dead end.
4. **Honest over impressive.** No "best", no percentages, no promised callbacks, no guarantees about visas or admission.
5. **Always readable as text.** Every card has a plain-text fallback, so it never breaks on channels that can't draw it.
6. **Calm and premium.** Soft shadows, generous spacing and short purposeful motion. Nothing flashy.

---

## 2. Colour

The **tenant's brand colour** is the only accent. Everything else is neutral.

| Token | Value | Use |
|---|---|---|
| `--zk-accent` | tenant colour (Admizz `#2563eb`) | Buttons, selected state, progress, focus ring |
| `--zk-accent-soft` | accent at 8% | Selected backgrounds, ghost buttons |
| `--zk-accent-mid` | accent at 20% | Hover borders |
| `--zk-accent-dark` | accent mixed with navy | Text on soft accent backgrounds |
| `--zk-ink` | `#0f172a` | Main text |
| `--zk-ink-2` | `#334155` | Body text |
| `--zk-muted` | `#64748b` | Labels, subtitles |
| `--zk-faint` | `#94a3b8` | Notes, sources |
| `--zk-line` | `#e2e8f0` | Borders, dividers |
| `--zk-bg` | `#f8fafc` | Subtle fills |
| `--zk-ok` | `#15803d` | Pass, done, strong fit |
| `--zk-warn` | `#b45309` | Partial, needs attention |
| fail | `#b91c1c` | Fail marks only |

Rules:
- Never hard-code a brand colour. Always use `--zk-accent*`.
- Status colours (ok / warn / fail) mean status only. Never use them for decoration.
- All text meets **WCAG AA (4.5:1)** on white. Check any new colour before adding it.

---

## 3. Typography

Inherits the host's font; the widget defaults to Inter.

| Element | Size | Weight |
|---|---|---|
| Card title | 15px | 650 |
| Card subtitle | 12.5px | 400, muted |
| Body / rows | 13–13.5px | 400–600 |
| Small labels, notes | 11–12px | 500–700 |
| Big numbers (slider, cost total) | 24–28px | 700, tabular digits |

- Numbers that change live use `font-variant-numeric: tabular-nums`, so they don't jump.
- Money is formatted by code in the catalog's currency, in whole units (`backend/app/services/money.py`). NPR uses Indian digit grouping (`NPR 25,00,000`); others use their symbol (`£20,000`) or code (`AUD 20,000`).

---

## 4. Shape and spacing

| Thing | Value |
|---|---|
| Card radius | 18px (16px on mobile) |
| Inner elements (tiles, options, rows) | 14–16px |
| Buttons, inputs | 12px |
| Pills (tier badges, chips) | fully rounded |
| Card padding | 16px (14px on mobile) |
| Gap between items | 8–12px |
| Shadow | `--zk-shadow`, one soft layered shadow; never heavy |
| Max card width | 520px inside the chat |

---

## 5. Card anatomy

```
┌───────────────────────────────────────┐
│ Title                                 │  ← from the registry, never the LLM
│ Subtitle (optional)                   │
│ ↻ Updated because your budget changed │  ← only when re-shown with new content
│                                       │
│   card body (one component per type)  │
│                                       │
│ [ Primary button ]                    │  ← one primary action at most
│ Source: page-a, page-b                │  ← knowledge-base cards only
└───────────────────────────────────────┘
```

- **One primary button per card at most.** Secondary actions use the ghost style.
- **Next-step buttons** go in a separate `quick_chips` row under the card, max 3.

---

## 6. States

| State | What the student sees | Applies to |
|---|---|---|
| Loading | Skeleton with pulsing dot and shimmer bars | All cards while building |
| Answered | Folds into a one-line summary: ✓ question, answer, Edit | `choice_cards`, `range_slider`, `journey_cards`, `lead_form` |
| Editing | Card reopens with the previous answer preselected | Same four |
| Locked | Dimmed (72% opacity), no longer tappable | Input cards, match cards, profile summary, chips, once a newer card replaces them |
| Self-contained | Stays fully usable forever | Stepper, checklist, calculator, timeline, accordion, info, comparison |
| Updated | "↻ reason" strip at the top | Any card re-shown because profile inputs changed |
| Error or unknown | Plain `fallback_text`, never a crash | All cards |

---

## 7. Motion

| Animation | Use | Duration |
|---|---|---|
| `zk-rise` | Card or item enters (fade + 10px up) | 0.3–0.4s |
| Stagger | Items in a list enter one after another | 45–70ms apart |
| `zk-pop` | Tick or checkmark appears | 0.3–0.4s |
| `zk-shimmer` / `zk-pulse` | Loading skeleton | loops |
| Hover lift | Tappable tiles and options rise 1–2px | 0.15–0.2s |

- One easing everywhere: `--zk-ease` (`cubic-bezier(0.22, 1, 0.36, 1)`).
- **All motion turns off under `prefers-reduced-motion`.**
- Motion explains a change. Never animate just for decoration.

---

## 8. Mobile and touch

- Every tappable control is **at least 44px tall** on phones and touch devices (48px for main tiles and buttons).
- Choice grids become 2 columns.
- Cards use the full width under the assistant avatar.
- Wide tables scroll sideways, with the first column sticky and soft edge shadows showing there's more.

---

## 9. Accessibility

- Visible focus ring (2px accent outline) on every button, input and slider.
- The profile progress bar uses `role="progressbar"` with values. Loading skeletons use `role="status"`, and wide tables are a focusable, labelled scroll region.
- New cards are announced to screen readers (`BlockAnnouncer`).
- Status marks (✓ ✗ ~) have screen-reader labels.
- Screen-reader-only text uses `.zk-sr-only`.
- Never use colour alone to show status. Always pair it with a mark (✓, ✗, ~) or a word.

---

## 10. Writing (copy)

Intro sentences are written by code (`education_leadins.py`), in English. Other languages fall back to the LLM, which follows the student's language.

**Do:**
- Keep it to one short sentence before a card.
- Say why you're asking ("To suggest countries I need a few details. Let's start with your yearly budget.").
- Use plain words: "fit", "costs", "requirements".
- Admit gaps: "I don't have that detail yet. A counselor can help you with it."

**Don't:**
- Say "best", "guaranteed" or "high chance", or give percentages for fit or admission.
- Promise that someone will call or email.
- Mention universities or programs unless the catalog actually has them.
- Repeat what the card already shows.
- Ask again for something the student already answered.

**Labels:**
- Titles in sentence case ("Countries that match your profile").
- Buttons start with a verb ("Check my eligibility for UK", "Talk to a counselor").
- Fit tiers are always exactly: Strong fit · Good fit · Possible fit · Needs review.

---

## 11. Checklist for a new or changed card

- [ ] Uses only `--zk-*` tokens; no hard-coded brand colour
- [ ] Title from the registry; data built by code and validated
- [ ] Has a useful `fallback_text`
- [ ] Loading, locked and error states work
- [ ] At most one primary button
- [ ] 44px touch targets; works at 320px width
- [ ] Focus ring visible; status not shown by colour alone
- [ ] Motion off under reduced-motion
- [ ] Copy follows section 10
- [ ] Added to the [card catalog](./generative-ui-card-catalog.md)
