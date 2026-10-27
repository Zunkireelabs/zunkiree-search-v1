# Generative UI — Card Catalog (education)

Every card the education counselor can show, what it's for, and when it appears.
Applies to tenants with `website_type = "education"`.

**Source of truth is the code.** This doc is a readable map of it:

| What | Where |
|---|---|
| Card types, data shapes, versions | `backend/app/schemas/ui_blocks.py` (`UI_TYPES`) |
| Question → card map | `backend/app/services/education_ui_registry.py` (`INTENTS`, `detect_intent`) |
| Card + companions per question | `backend/app/services/education_compositions.py` (`COMPOSITIONS`) |
| Knowledge-base answer cards | `backend/app/services/education_kb_blocks.py` |
| Intro sentence for each card | `backend/app/services/education_leadins.py` |
| Widget component per card | `widget/src/components/blocks/BlockRenderer.tsx` (`REGISTRY`) |

If you change a card, change the code first, then update this doc.

---

## How a card gets chosen

1. **Code rules first.** `detect_intent` matches the question with keyword rules, before any LLM call. For example, "which countries fit me?" always gives `match_cards`.
2. **Knowledge-base shapes second.** An open question whose answer has a shape (steps, a checklist, dates, a list of services) becomes a stepper, checklist, timeline or accordion, built only from the tenant's knowledge base.
3. **LLM last.** For anything else, the LLM may pick a card, but only from this catalog. It never writes card JSON. Code builds and validates the data.
4. **Taps go back through code.** A tap is checked against the card it came from, saved to the profile, and the card is re-run.

---

## The cards

### Asking the student (input cards)

These collect profile answers. Once answered, they **fold into a one-line summary** with an Edit button, and they **dim** when a newer card replaces them.

| Card | What it looks like | When it appears | Tap action |
|---|---|---|---|
| `journey_cards` | 3–5 welcome tiles with icon, title and description | Greeting ("hi") or start of chat. Tiles needing country data are hidden if the tenant has no catalog. | `start` |
| `choice_cards` | Grid of option cards, single or multi-select | Asking countries, study level, intake, or "which country?" | `select` |
| `range_slider` | Big number + slider | Asking the yearly budget | `set_value` |
| `lead_form` | Name, email, phone (all required), prefilled if known | "Talk to a counselor", "call me", "apply now" | `submit` |

**Welcome tiles (fixed):** Find the right country · Check my eligibility · Estimate my costs · How to apply · Talk to a counselor.

### Answering the student (result cards)

| Card | What it shows | When it appears | Uses from profile |
|---|---|---|---|
| `match_cards` (v2) | Countries grouped by fit tier, each with pass / partial / fail reasons | "Which countries fit me?" | budget, English score, academic score, intake |
| `info_card` | Country heading + label/value rows | "Tell me about Canada" | none |
| `comparison_table` | 2–3 countries side by side | "UK vs Canada", "which is cheaper" | none |
| `eligibility_meter` (v2) | Verdict + pass/fail checks | "Am I eligible for the UK?" | English score, academic score |
| `cost_calculator` | Adjustable cost parts with a live total | "How much does Australia cost?" | none |
| `profile_summary` | What we know + what's missing | "What do you know about me?" | all profile fields |
| `course_results` | Up to 6 courses with university, fee, length, intake and IELTS; how many matched and what was searched | "MSc data science in the UK", "which universities offer law", "courses at Essex" | study level (dropped if it leaves nothing) |
| `university_card` | One university's location, intakes, course count, tuition range and entry requirements | "Tell me about Arden University", or a tap on a course | none |

**Course and university cards** only exist for a tenant whose catalog has courses; for any other tenant these questions behave as before. Courses are searched by fixed filters (country, level, subject words, one university) and listed lowest yearly fee first, one course per university for a broad search; the card says so ("Lowest fee first"). A fee is shown as the source states it: a plain yearly figure, a whole-course total, or the source's own wording ("from £9,400 per year ..."); it is never computed or converted, and never compared with the student's budget (different currency). Every course card carries "Fees come from Admizz's website and can change. A counselor can confirm them." (Admizz confirmed on 2026-10-27 that we may use its website numbers; the pages themselves say fees can change.) Cards built from the country sample figures carry the separate "Indicative figures" note while the catalog is not `verified` Tapping a course opens its university (`open_university`).

**Fit tiers** (`match_cards`): Strong fit · Good fit · Possible fit · Needs review.
A tier describes how well the student's own details line up. It is **not** a chance of admission or of a visa, and it's never shown as a percentage.

### Knowledge-base answer cards

Built only from the tenant's own knowledge base. Every item must be traceable to the retrieved text, and the source pages are shown at the bottom. If the knowledge base doesn't clearly answer, no card is shown and the student gets the honest "I don't have that detail yet" plus a counselor button.

| Card | Answer shape | Example question |
|---|---|---|
| `stepper` | A process (ordered steps) | "How do I apply?" |
| `checklist` | Things to prepare | "What documents do I need?" |
| `timeline` | Dates, deadlines | "When are the intakes?" |
| `accordion` | Services or options | "What services do you offer?" |

Single-fact answers ("is it free?") have no shape and stay plain text.

### Next-step buttons

| Card | What it shows | When it appears |
|---|---|---|
| `quick_chips` | Up to 3 buttons under a result card | After most result cards (see compositions below) |

Buttons come from a **closed list**:
Which countries fit me? · What do you know about me? · Update my budget · Talk to a counselor · Compare A and B · Check my eligibility for X · Estimate costs for X · Quick facts: X · Browse courses in X (only where the catalog has courses).
A button only appears if the card it leads to can actually be built right now.

---

## Compositions (what appears together)

The same question with the same profile always gives the same cards, in this order:

| Question type | Cards shown |
|---|---|
| Which countries fit me? | `profile_summary` → `match_cards` → `quick_chips` |
| Compare | `comparison_table` → `quick_chips` |
| Eligibility | `eligibility_meter` → `quick_chips` |
| Country facts | `info_card` → `quick_chips` |
| Costs | `cost_calculator` → `quick_chips` |
| My profile | `profile_summary` → `quick_chips` |
| Courses / universities in general | `course_results` → `quick_chips` (Talk to a counselor) |
| A named university | `university_card` → `course_results` (its courses) → `quick_chips` |
| Anything else | the single card |

Special cases:
- **"Which country is best?" with no details yet:** a sentence explaining why we need details, then the budget slider.
- **Knowledge base has no answer:** the "I don't have that detail" sentence plus a counselor button.

---

## Every card carries

| Field | Purpose |
|---|---|
| `block_id` | Same content always gives the same id, so taps can be matched to the card |
| `type` + `schema_version` | Which card, which version |
| `title` / `subtitle` | Owned by the registry, never written by the LLM |
| `data` | Validated against the card's schema |
| `fallback_text` | Plain-text version for channels that can't draw cards (Instagram, voice, Orca) |
| `changed_because` | Shown as "↻ …" when a card is re-shown with new content because the profile changed |
| `sources` | Knowledge-base pages the content came from |
| `answered` | What the student submitted; makes input cards fold into a summary |

---

## Adding a new card (checklist)

1. Add the data model and a `UISpec` entry in `backend/app/schemas/ui_blocks.py` (description, when to use, actions, collapsible / dims).
2. Add the TypeScript type in `widget/src/components/blocks/types.ts` and a component in `widget/src/components/blocks/`.
3. Register it in `REGISTRY` (and `COLLAPSIBLE` / `DIM_WHEN_LOCKED` if needed). The parity tests fail if backend and widget disagree.
4. If a question should always open it, add an intent in `education_ui_registry.py` and a tool in `education_tools.py`.
5. Add an intro sentence in `education_leadins.py` and, if useful, a composition and buttons in `education_compositions.py`.
6. Follow the [design guideline](./generative-ui-design-guideline.md).
7. Add the card to this doc.

**Changing a card's data shape:** bump its `version` and add an upgrader, so cards saved in old chats still render.
