# Generative UI Education Advisor: Case Study Assessment and Adaptation Plan

**Date:** 2026-10-12 · **Branch:** `feature/generative-ui-education` · **Status:** assessment only; no phase approved for implementation.
**Source compared:** `temp-ss/Generative-UI-Case-Study.pdf` ("Generative UI: case study and implementation playbook", 14 pages; TripBuddy Pattern A, component-registry demo Pattern B, LangChain guide, guardrails, handoff checklist).

### Evidence legend
- **[CODE]** read directly in the code (path and line given)
- **[TEST]** confirmed by a test run in this session
- **[HYPOTHESIS]** follows from reading the code but hasn't been reproduced by running it
- **[BLOCKED]** waits on real catalog data or a product decision
- **[NOT CHECKED]** not inspected in this session

Test run this session: `cd backend && .venv311/bin/python -m pytest tests/ -q -k "education or widget_history or money or auto_create"` gave **676 passed**, 784 deselected **[TEST]**. The full backend suite, the widget typecheck and the widget tests were **[NOT CHECKED]**.

---

## A. Current architecture

**Request flow [CODE]:**
1. The widget (`widget/src/components/Widget.tsx`) creates `session_id` with `crypto.randomUUID()` and stores it in localStorage as `zk_session_<siteId>` (line 125). It posts to `POST /api/v1/query/stream` (line 238) with `question`, `session_id` and an optional `block_action`.
2. `QueryRequest` (`backend/app/api/query.py:187`) caps `question` at 500 characters. `session_id` is optional, with no format check.
3. When `customer.website_type == "education"` (`api/query.py:737`), the request goes to `EducationAgentService.process_agent_stream` (`backend/app/services/education_agent.py:184`).
4. A turn then runs:
   1. `get_catalog(site_id)`, then `DbEducationMemory.load_profile` and `load_history`.
   2. Tap check: `validate_block_action` (`education_actions.py`) against the stored block from `find_block`. A rejected tap is dropped and the turn continues as text.
   3. `apply_block_action`, which writes only whitelisted fields, then the email merge for a submitted contact, then `save_profile` and `mark_answered`.
   4. Routing:
      - `resolve_country_switch`
      - `_turn_intent`: taps, tiles, chips, a bare "ok", then `detect_intent` (regex rules, `education_ui_registry.py`)
      - `resolve_refinement`
   5. When an intent matches: `execute_education_tool` builds a validated block, `compose()` adds the profile summary and next-step chips, and `leadin_for()` writes the sentence in code. In English, a card turn makes no LLM call when a code lead-in exists.
   6. When nothing matches: `classify_shape` (LLM, temperature 0, cached) → `_retrieve_and_rank` (Pinecone) → `kb_block` (LLM restructures knowledge-base text, every item checked against the source), or `counselor_block` on a miss.
   7. Otherwise the OpenAI tool loop: at most 3 iterations, `max_tokens=200`, `temperature=0.2`, `EDUCATION_TOOLS` (10 tools). Free text passes `check_answer` (`education_grounding.py`).
   8. Persist with `save_profile` and `append_message` (text plus blocks), then send `done` with `profile_progress`.

**SSE events [CODE]:** `tool_call`, `ui_pending`, `ui_block`, `token`, `done`.
**Restore [CODE]:** `GET /api/v1/widget/history/{site_id}/{session_id}` (`backend/app/api/widget.py`) returns the last 50 messages with their blocks and the profile progress.

**Registry and validation [CODE]:**
- `UI_TYPES` holds 15 `UISpec` entries (`backend/app/schemas/ui_blocks.py`), with Pydantic data models, per-type `version`, `upgraders` and `upgrade_stored_block`. Every block has `fallback_text`.
- The widget's `BlockRenderer.tsx` has `REGISTRY`, `COLLAPSIBLE`, `DIM_WHEN_LOCKED`, the `isSupported` version gate and `BlockErrorBoundary`. An unknown or unsupported block falls back to text.
- There are parity test files: `test_education_widget_parity.py` and `test_education_memory_schema_parity.py`.

**State [CODE]:**
- Tables `visitor_profiles` and `widget_messages` (migration `042_education_agent_memory.sql`), keyed by `customer_id` + `session_id`.
- `profile["ui_state"]` is the result UI on screen; `profile["shown"]` is the block cache that keeps answers consistent.
- The LLM sees the last 10 messages; the widget restores the last 50.

**Data [CODE]:**
- `get_catalog()` is a provider seam (`set_catalog_providers`, `education_catalog.py`). Today it loads JSON from `app/data/education_catalogs/<site_id>.json`.
- `admizz-test.json` has `"status": "PLACEHOLDER"`, sample numbers and currency `"$"` (USD). It is not Admizz data.
- `University` and `Course` models exist, with no data (`education_catalog_models.py`).
- Money lives in `services/money.py` (`Money`, `format_money`, Indian grouping for NPR).
- Fit tiers come from rules in `fit_countries`: no weights, no percentages.

**Flags [CODE]** (`backend/app/config.py:49-61`, all default `True`): `education_validate_block_actions`, `education_compositions`, `education_template_leadins`, `education_grounding_check`.

**Dependencies [CODE]:** `backend/requirements.txt` has `openai`, `pydantic`, `pinecone` and `sqlalchemy`. LangChain and LangGraph are neither listed nor imported.

**Naming [CODE]:** the intent is already `recommend_country` (`education_ui_registry.py:30`). `country_matches` survives only in the tool name `show_country_matches`. No rename is needed.

---

## B. Case-study adaptation matrix

| PDF concept | Our equivalent | Gap | Verdict |
|---|---|---|---|
| Pattern A: guided slots and chips | `SLOT_ORDER`, `_next_card`, `choice_cards`, `range_slider`, `missing_slots` [CODE] | Field of study and English score are asked as text only | **Adapt**: optional English-score card |
| Pattern A: model chooses chips per step | Fixed option sets (`STUDY_LEVELS`, catalog intakes) [CODE] | None | **Reject**: it would let the LLM invent options |
| Pattern B: component registry | `UI_TYPES` + widget `REGISTRY` + parity tests [CODE] | Already stronger than the PDF | **Reuse** (done) |
| Model returns `[{component, props}]` | The LLM picks a tool; code builds the props [CODE] | None | **Reject**: LLM-written props would break grounding |
| Structured output, then validate | `build_block` validation [CODE]; tool args JSON-parsed | No schema-constrained intent classifier | **Adapt**: enum-only fallback classifier |
| Real data through tools | Catalog tools, knowledge-base retrieval, profile [CODE] | Placeholder catalog; no universities or courses | **[BLOCKED]** |
| Text fallback | `fallback_text`, `BlockErrorBoundary`, `KB_MISS` [CODE] | Fallback rate isn't measured | **Adapt**: metrics |
| Message history | `DbEducationMemory` in Postgres [CODE] | Already fixes PDF problem 4 (in-process `Map`) | **Reuse** (done) |
| UI state stored with messages | `ui_state`, `shown`, `answered` [CODE] | None | **Reuse** (done) |
| Tap = input | `block_action` + `validate_block_action` [CODE] | Ours is validated; the PDF's is not | **Reuse** (done) |
| SSE + `ui_update` event | `ui_block` re-sent with `changed_because` [CODE] | No in-place update event | **Investigate**: low value |
| Escape every string (PDF problem 2) | `Markdown.tsx` runs `escapeHtml` and then `dangerouslySetInnerHTML` [CODE] | Rests on one function, with no XSS test | **Adapt**: add a test (Phase 1) |
| Restrict origins and rate-limit (PDF problem 6) | Global `ALLOWED_ORIGINS` CORS (`main.py:108`); per-site check `_validate_origin` [CODE] | The education path skips the per-site check; no rate limiter found | **Adapt** (Phase 1) |
| Missing streaming route (PDF problem 1) | `/query/stream` exists [CODE] | none | n/a |
| URL query-string state (PDF problem 5) | Not used [CODE] | none | n/a |
| Per-site enabled components | Not present [CODE] | A tenant can't turn cards off | **Investigate** |
| Regression set of 50–100 real queries | `test_education_phrasing.py`, `test_education_consistency.py`, `tests/golden/` [CODE] | Synthetic phrasings, not real logs | **Adapt** (Phase 2) |
| Metrics (fallback rate, time to first component) | `[EDU]` log lines only [CODE] | No metrics | **Adapt** (Phase 4) |
| LangGraph `push_ui_message` / React | n/a: the widget is an IIFE bundle | The PDF itself says to use your own SSE for a widget | **Reject** |

---

## C. Target architecture (same shape, tightened)

```
message / tap
 → validate tap (validate_block_action)                      [exists]
 → intent: follow-up → rules → enum-only LLM classifier      [NEW, flag off by default]
 → data: catalog tools / knowledge-base retrieval / profile  [exists; catalog provider swapped later]
 → build block(s) in code + compose                          [exists]
 → validate (build_block, grounding check)                   [exists]
 → SSE ui_block / token / done                               [exists]
 → widget renderer (REGISTRY, version gate, fallback)        [exists]
 → persist profile + ui_state + transcript                   [exists]
 → per-turn metrics event, no PII                            [NEW]
```

No LangChain or LangGraph (see G).

---

## D. Component registry plan

**Keep (15) [CODE]:** `choice_cards`, `range_slider`, `journey_cards`, `lead_form`, `quick_chips`, `match_cards` (v2), `profile_summary`, `info_card`, `comparison_table`, `eligibility_meter` (v2), `cost_calculator`, `stepper`, `checklist`, `timeline`, `accordion`.

**Mapping the brief's vocabulary onto them:**

| Candidate concept | Maps to |
|---|---|
| ProfileSummary | `profile_summary` |
| AdaptiveQuestion / ChoiceGroup | `choice_cards` |
| RangeSlider | `range_slider` |
| CountryRecommendation | `match_cards` |
| CountryComparison | `comparison_table` |
| EligibilityCheck | `eligibility_meter` |
| FeeTable / CostBreakdown | `cost_calculator` |
| IntakeTimeline | `timeline` |
| Checklist | `checklist` |
| FAQ / KnowledgeAnswer | `accordion`, or knowledge-base text |
| ActionGroup | `quick_chips` |
| CounselorBooking / ContactCTA | `lead_form` |
| Evidence | the `sources` field |

Loading, empty and error states already exist: `BlockSkeleton`, `KB_MISS` plus counselor, and `fallback_text`.

**Fix (Phase 3):**
- `check_eligibility` (`education_catalog.py`) adds "Proof of funds" as `ok: False`, so it renders like a failed requirement [CODE]. Bump to v3 with an `info` status and an upgrader.
- The `UISpec` docstring says `allowed_actions` is "not enforced yet", but `validate_block_action` already enforces it [CODE]. Correct the comment.

**Add later [BLOCKED]:** `university_results` and `course_results`, built only from `University`/`Course` records supplied through `get_catalog()`, each showing its `source`. Without data, the existing "don't have that detail" path stays.

---

## E. Intent and state plan

- **Today [CODE]:** regex rules, then the follow-up resolvers, then the block cache (`_cached`), with golden snapshots. A paraphrase the regexes miss goes to the LLM tool loop, which may choose a different card [HYPOTHESIS: not measured].
- **The brief's four phrasings:** "Where should I go…" matches `_MATCHES` (`where (should|can|do) i (study|go)`) [CODE]. Whether all four resolve to `recommend_country` today is **[NOT CHECKED]**. Phase 2 adds them as tests.
- **Add (Phase 2):** a `classify_intent` fallback after the rules.
  - One temperature-0 call using OpenAI `response_format` json_schema, with an enum of exactly the `INTENTS` keys plus `none`.
  - Cached the same way as `classify_shape`.
  - Accepted only if the value is in the enum and resolves through `tool_for_intent`.
  - Behind a new flag that defaults to off.
- **Budget follow-up:** master's → 25 lakh → "below 20 lakh". This uses `resolve_refinement` → `set_field("budget")` → re-run `recommend_country` [CODE]. With `admizz-test` in USD, lakh amounts are rejected by `_currency_ok`, which is correct. A working demo is **[BLOCKED]** on an NPR catalog.
- **Add (Phase 3):** store `budget_currency` in the profile. Today the budget is a bare number taken to be in the catalog's currency [CODE].

---

## F. Data and grounding plan

- Keep the `get_catalog()` seam. The real Admizz catalog arrives either as a JSON file with `status: "verified"` or as a new `CatalogProvider`. No migration until a real source exists.
- Missing data keeps today's rules: no card, `KB_MISS` plus counselor, and the grounding check drops unsupported sentences [CODE].
- Free-text knowledge-base answers have no source attribution: `done.sources` is always `[]` (`education_agent.py:473`) [CODE]. Phase 3 fills it.
- The placeholder catalog only logs a warning when not verified (`education_catalog.py:159`) [CODE]. Phase 3 adds a guard so a non-verified catalog can't serve a live tenant. The exact mechanism needs a product decision.

---

## G. Framework decision: keep the current orchestration

**Recommendation:** don't introduce LangChain or LangGraph unless a concrete requirement appears that the current code can't meet cleanly.

**Evidence:**

| Criterion | Current code | + LangChain | + LangGraph |
|---|---|---|---|
| Fit | Python, raw `openai` SDK, deterministic first [CODE] | Wraps the same tool loop | Graph over the same steps |
| Effort / risk | none | New dependency, rewrites the agent loop | Large rewrite; duplicates `DbEducationMemory` with checkpointers |
| LLM calls per card turn | 0 in English [CODE] | Same or more | Same or more |
| Structured output | Available natively (`response_format`) | `withStructuredOutput`, same thing | Same |
| State | Postgres profile + `ui_state` + transcript [CODE] | `RunnableWithMessageHistory`, needs a DB backend anyway | Checkpointer duplicates ours |
| Widget fit | Own SSE into an IIFE [CODE] | n/a | Its React UI path doesn't fit; the PDF agrees |
| Testability | 676 education tests pass offline [TEST] | Mocks get harder | Harder |

Repo constraint: `CLAUDE.md` says platform machinery belongs in Orca, and the brain runtime is still an open decision (vision O1). Adding a framework here would pre-empt that.

**What we adopt from the PDF:** the concepts only: structured output (the enum classifier), "use when" registry text (`UISpec.when_to_use` exists), the regression set and metrics.

---

## H. Phased roadmap

Each phase is a separate PR to `stage`, gated by a flag where behaviour changes. The brain window reviews and merges. Shared rollback: turn the flag off or revert the PR.

### Phase 1: security and privacy (no UI or prompt change)

**1.1 Email merge can import another student's profile [TEST: reproduced 2026-10-12; FIXED 2026-10-13 by product decision (merge off until email is verified), uncommitted]**

> Fix: the merge call is removed from `education_agent.py`; `find_profile_by_email` and `merge_profiles` are kept for a future verified merge. The old test is now `test_contact_submit_does_not_link_profile_from_another_device`; the production-flag regression tests are in `tests/test_education_email_merge.py`. Trade-off: a student on a new device starts with an empty profile.

> Reproduced: a stranger opens the counselor form in their own session, submits the victim's email, then asks "what do you know about me?" and sees the victim's countries, budget and English score (the victim's phone is not copied). Not fixed because `tests/test_education_agent.py::test_contact_submit_links_profile_from_another_device` defines this cross-device merge as intended behaviour; that test runs with tap validation off (`tests/conftest.py`). Options: (a) turn the merge off until the email is verified; (b) merge only after verification (whether the existing `services/verification.py` email flow can be reused is not checked).

**Code involved:**
- `backend/app/services/education_agent.py:216-224`: a `lead_form` submit sets `profile["contact"]`.
- `DbEducationMemory.find_profile_by_email` (`education_memory.py:63`): looks up by tenant + email, excluding the current session.
- `merge_profiles` (`education_profile.py:174`): fills gaps in the current profile from the other one.

**Reproduce:**
1. Session A sets budget, scores and countries, then submits the form with `a@x.com`.
2. Session B, in a fresh browser, submits the form with `a@x.com`, then asks "what do you know about me?".

**Expected today:** B's `profile_summary` shows A's data.
**Expected after the fix:** no cross-session merge until the email is verified, or the merge is turned off.
**Regression test:** in `backend/tests/test_education_agent.py`, use `InMemoryEducationMemory` with two sessions on the same email and assert that B's profile does not get A's fields.

**1.2 A missing `session_id` shares one profile per tenant [TEST: reproduced and FIXED 2026-10-12, uncommitted]**

> Reproduced through `submit_query_stream`: two visitors with no `session_id` were both stored under key `''`, and visitor B's counselor form came back prefilled with visitor A's name, email and phone. Fixed with `is_valid_session_id` (`services/education_memory.py`): the id must be non-blank and at most 100 characters (the column size); it is NOT forced to be a UUID. Education requests that fail the check get 400 `INVALID_SESSION_ID` on `/query/stream` (`api/query.py`) and on `/widget/history` (`api/widget.py`). Other website types are unchanged. Tests: `tests/test_education_session_id.py`. The fix text below ("non-UUID") is superseded by this note.

**Code involved:**
- `api/query.py:190`: `session_id` is optional.
- `api/query.py:741`: passes `session_id=query.session_id or ""`.
- The memory functions then key on `(customer_id, "")`.

The widget always sends a UUID (`Widget.tsx:125`), so the risk comes from direct or third-party API callers.

**Reproduce:** two POSTs to `/query/stream` for an education site with no `session_id`. The second turn sees the first's profile.
**Expected after the fix:** education returns 400 for a missing or non-UUID `session_id`. The history endpoint validates the UUID format too.
**Regression test:** a new test for the route, covering missing, empty and malformed values.

**1.3 The education stream skips the per-site origin allowlist [TEST: reproduced and FIXED 2026-10-13, committed]**

> Fixed: `/query/stream` (education branch) and `/widget/history` now call `require_allowed_origin` (`backend/app/api/origin_guard.py`), which uses the same `QueryService._validate_origin` rule as the other chat paths. An unapproved website gets 403 `ORIGIN_NOT_ALLOWED`; a request with no Origin header is let through (server to server, same origin), so this is a browser-side control, not authentication. Other tenant types are unchanged. Tests: `backend/tests/test_education_origin.py` (15, incl. a real HTTP check of the history route). **Read-only DB check 2026-10-13:** the shared database has one education tenant, `admizz-test`, whose approved list is `localhost` only, so no real tenant is affected. **Go-live requirement:** the real Admizz website must be added to that tenant's `domains` list, or its widget will be refused. Production `ALLOWED_ORIGINS` is `*` (read-only check of the VPS `.env`), so browser CORS does not limit websites; this guard does. An Origin of `null` (sandboxed iframe, file://) is refused, as on the other paths.

Original finding:

**Code involved:**
- `api/query.py:737` returns from the education branch before line 787, where the generic path passes `origin` into `process_query_stream`.
- That generic path calls `_validate_origin` (`services/query.py:390`).
- Note that `_validate_origin` only runs `if origin` is present, so server-side callers without an Origin header skip it on every path.

**Reproduce:** POST from a non-allowlisted Origin to an education site.

**Expected:**
- **Today:** the education site answers.
- **On a non-education site:** the same request is refused.
- **After the fix:** education matches the other paths, and the history endpoint gets the same check.

**Regression test:** a route test with an allowed Origin and a disallowed one.

**1.4 No rate limiting on `/query/stream` or `/widget/history` [FIXED, TEST]**

**Fixed:** `app/utils/rate_limit.py`, an in-process rolling window per tenant and visitor address (last `X-Forwarded-For` entry, which the proxy adds). Education only, on `/query/stream` and `/widget/history`: 20 chat messages and 60 history reads per minute, then 429 `RATE_LIMITED` with `Retry-After`, before any AI call. The non-streaming `POST /query` (found in the pre-PR audit to reach the generic search path unlimited) now refuses education sites with `400 USE_STREAM_ENDPOINT` before any AI call or `query_logs` write. Tests: `tests/test_education_rate_limit.py` (16). Limits: counters are per worker (production runs 2, so the real ceiling is up to double) and reset on restart; many students behind one shared address share one count.

**Code involved:** `backend/app/main.py` and the two routes.
**Reproduce:** a burst of requests is never throttled.
**Expected after the fix:** per-IP and per-site limits that return 429.
**Regression test:** a burst test asserting 429.

**1.5 Student text in logs [TEST: reproduced and FIXED 2026-10-13, committed]**

> Fixed for education only: the `[QUERY-TRACE]` / `[QUERY-STREAM]` lines (`api/query.py`) now log the question's length instead of its text (other tenants unchanged); the `[EDU]` tool lines (`education_agent.py`) log argument names, not values; uvicorn's access log hides the session id in `/widget/history/<site>/<session>` (`app/utils/log_redaction.py`, installed in `main.py`). Tests: `tests/test_education_log_privacy.py`. Not covered: `logger.exception` in `/query/stream` and the other tenants' log lines.

Original finding:

**Code involved:** `api/query.py:536`. `[QUERY-STREAM]` logs `question[:80]` at WARNING before routing, and `api/query.py:230` (`[QUERY-TRACE]`) does the same on the non-stream path.
**Expected after the fix:** education turns log length and language only, like `[EDU] no_rule_match` does (`education_agent.py:289`).
**Regression test:** a `caplog` test asserting the question text is absent.

**1.6 XSS through markdown [TEST: no script injection found; display bug FIXED 2026-10-13, committed]**

> Tested with 21 attack strings (`<script>`, `<img onerror>`, `javascript:` and `data:` links, quote breakouts, tables, lists, headings): none produced an active tag, attribute or non-http(s)/mailto link. Found and fixed a display bug: bold/italic/code and the email auto-link ran inside a link's address, injecting tags into `href` and nesting a link inside a link. Links are now set aside before formatting (`renderInline` in `widget/src/components/Markdown.tsx`). Tests: `widget/src/components/Markdown.test.ts`. Not covered: other places that render student or AI text (the lead form values, block titles) were not audited; React escapes them by default.

Original finding:

**Code involved:** `widget/src/components/Markdown.tsx:7` (`escapeHtml`) and line 176 (`dangerouslySetInnerHTML`).
**Expected:** `<img onerror>` and `javascript:` links render as inert text.
**Regression test:** a widget unit test with XSS payloads in assistant text, plus any link handling.

**Must not change in Phase 1:** card behaviour, prompts, schemas or flags beyond any new security flag.

### Phase 2: consistency
- **Objective:** the `classify_intent` enum fallback (flag off by default), and a regression set built from real `[EDU] no_rule_match` queries in `backend/tests/golden/`.
- **Files:** `education_ui_registry.py`, `education_agent.py`, `config.py`, `tests/test_education_phrasing.py`.
- **Acceptance:** the brief's four phrasings resolve to `recommend_country` / `match_cards` v2, and existing tests stay green.
- **Must not change:** the existing regex rules or the block schemas.

### Phase 3: correctness and polish
- **Changes:**
  - `eligibility_meter` v3 (info status, plus an upgrader)
  - `budget_currency` in the profile
  - `done.sources` for knowledge-base text answers
  - the `UISpec` comment fix
  - a non-verified-catalog guard
  - optional English-score card
- **Files:** `schemas/ui_blocks.py`, `education_catalog.py`, `education_profile.py`, `education_agent.py`, widget `blocks/EligibilityMeter.tsx`, `blocks/blockVersions.ts`, `blocks/types.ts`.
- **Acceptance:** version and upgrader tests, golden snapshots updated on purpose, and parity tests green.

### Phase 4: measurement
- **Objective:** a per-turn structured event recording:
  - intent source (`rule`, `followup`, `llm`, `kb`, `fallback`)
  - block types shown
  - time to first `ui_block`
  - taps and lead submits
- **No PII.** Metrics: fallback rate, intent/UI consistency, time to first useful response, guided-flow completion and lead conversion.

### Phase 5: real data [BLOCKED]
- A verified Admizz catalog with countries in NPR.
- Then `university_results` and `course_results`.
- A possible DB-backed `CatalogProvider` plus a migration, which needs production approval.

### Product gap outside the phases [BLOCKED: product decision]
Leads aren't delivered anywhere. The system prompt says "Nothing is sent to the team yet" (`education_agent.py:63`) [CODE]. Wiring delivery to a CRM or email needs a brain-folder decision.

---

## I. Priorities
- **Smallest useful next step:** Phase 1.1 and 1.2 (email merge, empty session). They are small changes with high privacy value and testable offline with `InMemoryEducationMemory`.
- **Independent:** Phases 2, 3 and 4 after Phase 1. Phase 1.6 is widget-only.
- **Blocked on catalog data:** Phase 5, the NPR/lakh demo, and university/course cards.
- **Needs migration, dependency or prod approval:** a DB catalog provider, a rate-limit dependency, and lead delivery.

## J. Release and go-live checklist

Status as of 2026-10-13, branch `feature/generative-ui-education`. An item is marked done only where it was checked in code, by a test, or by a read-only look; everything else is outstanding. Nothing in this branch has been deployed.

### Done (verified)
- [x] **Cross-session profile exposure closed.** No profile merge by email; blank or oversized `session_id` refused (`test_education_email_merge.py`, `test_education_session_id.py`).
- [x] **Student text kept out of the education logs.** Question text and session ids are not logged on the education paths (`test_education_log_privacy.py`). Not covered: knowledge-base error lines and `logger.exception` in `/query/stream`, which can carry AI output.
- [x] **Markdown injection tests.** 21 attack strings checked structurally (`Markdown.test.ts`).
- [x] **Website (Origin) check** on the education chat and `/widget/history` (`test_education_origin.py`). A request with no Origin header is allowed, as on every other chat path.
- [x] **Message limit** of 20 per minute per visitor address on `/query/stream` and 60 per minute on `/widget/history`, refused with 429 and `Retry-After` before any AI call (`test_education_rate_limit.py`).
- [x] **Scores keep their unit** (`education_scores.py`, `test_education_scores.py`). A typed score is read in code before the AI runs ("7 is my english score", "ielts 6.5", "3.64 gpa", "72%"); a GPA is stored with its scale and never as a percentage; an English score is only compared with the IELTS minimum when it is an IELTS score. Replayed with the real AI model (in memory) on the conversation that exposed the bug. Not covered: a bare reply with no unit or cue (for example just "7" after the bot asks), which still depends on the AI saving it.
- [x] **Tables exist.** `visitor_profiles` and `widget_messages` (migration 042) exist on the shared database (read-only table-name check; no rows read).

### Outstanding before the production widget is enabled
- [ ] **Confirm how the proxy reports the visitor address. NOT VERIFIED.** The limiter counts the last `X-Forwarded-For` entry, which Traefik is assumed to add. `traefik.yml` was not readable from the audit account, so this is unconfirmed. Check with authorized VPS access (read `forwardedHeaders`), or with a controlled staging test: send from two addresses and confirm the counts are separate, and confirm that a forged first `X-Forwarded-For` entry does not change the key. If this is wrong, every visitor shares one counter.
- [ ] **Add the real Admizz website to the tenant's approved domains.** Tenant `admizz-test` currently lists only `localhost`. Until the real domain is added, the widget gets `403 ORIGIN_NOT_ALLOWED`.
- [ ] **Replace the placeholder catalog with verified data.** `admizz-test.json` is `PLACEHOLDER`: USD, sample numbers, not Admizz data. The code only logs a warning for an unverified catalog, so nothing yet stops its numbers being shown as real facts. Do not enable for real students until the catalog is verified and a guard exists (Phase 3).
- [ ] **Build and verify lead delivery.** Submitted contact details are saved to the profile only. The assistant tells the student "Nothing is sent to the team yet" (`education_agent.py`). Do not promise that inquiries reach the Admizz team until delivery exists and is tested.
- [x] **`/query` refuses education tenants** with `400 USE_STREAM_ENDPOINT` before any AI call, log line or `query_logs` write, so student text cannot be stored there (`test_education_rate_limit.py`). Evidence checked before the change: 0 education rows in `query_logs` (count only), 0 non-stream `/query` requests in 72 hours of production access logs, and the only repo caller (`ZunkireeSearch.tsx`) is imported nowhere. An outside integration calling `/query` for an education site was not found, but cannot be ruled out; it would now get the 400.
- [ ] **Replace the GPA conversion with Admizz's own rule.** A GPA is converted to a percentage by a plain proportion (3.64 out of 4 is about 91%), and every card that uses it says "estimated". There is no official conversion, so this is a stand-in: change `gpa_to_percent` in `education_scores.py` to use Admizz's table.
- [ ] **Browser-level CORS.** Production `ALLOWED_ORIGINS=*` is unchanged; the per-tenant Origin check above is what limits sites.

### Accepted limitations of the message limit
- Counters live in memory, per worker. Production runs 2 workers, so a visitor can reach about 40 per minute. A restart resets them.
- Visitors behind one shared address (a school or office network) share one count; a visitor with many IPv6 addresses can rotate.
- If a CDN is later placed in front of the proxy, all visitors behind it would share a counter unless the address logic is updated.
- Only education traffic is limited. `/query/autocomplete`, `/query/feedback` and the Instagram webhook are not. `api-spec.md` lists a 60 requests per minute per site limit on `/query`; no such limiter exists in the code.

## K. Admizz website source integration (local phase, 2026-10-13)

The live site (https://admizzeducation.com/) is connected to the chatbot **as links only**. Nothing from it became catalog data.

### What is connected
- **Source registry** `backend/app/data/education_sources/admizz-test.json` (36 entries): links to public Admizz pages with their titles, categories (guide, visa, cost, scholarship, test_prep, application, contact), kinds (answer, guide, article, service) and three separate dates: `sitemap_lastmod` (from the sitemap; not proof of accuracy), `published` (the page's own `datePublished`) and `checked` (the month a page says it was checked, e.g. "Checked in October 2026", only the 12 pages that say so; otherwise empty). Every entry is `verified: false`; the loader refuses `true`. Loader and selection: `backend/app/services/education_sources.py`, same seam as the catalog (plain-id check, cache, `register_sources` for tests).
- **Only https links on `admizzeducation.com` can ever be shown** (no other host, no `www`, no credentials, port, query or fragment, no characters that could break a Markdown link). Registry entries, retrieved knowledge-base page urls and redirect targets all pass the same check; titles are stripped of brackets, line breaks and web addresses.
- **One code-written link per reply**, appended after the grounding check (so it is streamed and saved with the message and survives a reload): `More on Admizz: [Title](url)`, plus `(checked October 2026)` only when the source states it. It is chosen by what was asked and the country in context, never because a country was merely selected: country-facts card to the guide, cost card to the cost page (or the visa page when the question is about the visa), free-text visa, cost, scholarship, test-prep or application questions to the best-matching page (country pages first, generic Admizz pages as a fallback), a knowledge-base answer to the page it was retrieved from, and a knowledge-base miss keeps the counselor card and adds the country guide only if one exists. No link for the profile, form, budget, welcome or compare cards, small talk, or a page already shown in the session.
- **Dry-run ingestion** `backend/scripts/ingest_education_sources.py` (see below).
- Tests: `test_education_sources.py`, `test_education_source_links.py`, `test_ingest_education_sources_script.py`, and a Markdown regression for the link line in `Markdown.test.ts`.

### What is NOT connected
- **Shared ingestion.** Nothing was written to Supabase or Pinecone; no embeddings were generated. `--write` exists only to refuse.
- **Verified catalog data.** The catalog is still the PLACEHOLDER; cost calculator and comparison cards use it only. `/universities` on the site is a partnership pitch (no university list) and `llms.txt` lists partner university NAMES only, so there are no verified courses, fees, minimums or intakes to import.
- **Country themes.** Not started.
- Retrieved knowledge-base chunks currently carry no page url (the 27 existing `admizz-test` chunks were ingested as text), so "link the page it came from" only starts working after an approved ingestion.

### Website sources stay `verified: false`
All 36. The pages mix undated figures, marketing claims and inconsistencies (for example visa processing "within 3 weeks" and "1-3 weeks" on one page). A link is a pointer to Admizz's own explanation, not proof that every claim on the page is right. The seven `/answers/*` pages are the best sourced (dated, citing GOV.UK) but are still unreviewed by us.

### How to run the dry run (from `backend/`)
`.venv311/bin/python -m scripts.ingest_education_sources` (all entries), `--only uk-guide` (one), `--registry path.json` (another file), `--existing snapshot.json --manifest manifest.json` (overlap with current chunks and a JSON manifest; see "Extraction quality, ingestion design and replacement plan" below). It reads only registry urls, honours robots.txt (an unreadable one stops the run), waits at least 1 second between requests, caps time and size, accepts HTML only, checks every redirect hop, and skips a page whose `sitemap_lastmod` is not newer than a valid `ingested_at`. It prints fetched / skipped / rejected / chunked / eligible counts. It touches no database, vector store or embeddings service and never rewrites the registry. Latest live run (2026-10-13): 36 fetched, 0 rejected, 141 chunks, 36 eligible.

### Approval needed before any persistent ingestion
A real write to the `admizz-test` namespace (Supabase `document_chunks` + Pinecone vectors, with paid embeddings) is a separate task and needs explicit approval after the dry-run report is reviewed. It should pass each page's canonical url and title through as `source_url` / `source_title`, record `ingested_at` in the registry, and be reversible by ingestion job.

### Findings and discrepancies from the audit
- The catalog loader is `app/services/education_catalog.py` (data in `app/data/education_catalogs/`); the new registry mirrors it.
- **The shared HTML extractor drops most of this site's content** (details and the fix in the next subsection). It was left unchanged for every other tenant.
- `done.sources` is always empty and the chat widget ignores it; card `sources` are title strings. Links therefore travel in the assistant text through the existing safe Markdown renderer.
- The website exposes no API, CMS or feed; the sitemap (261 urls with `lastmod`), `llms.txt` and the pages' JSON-LD are the only structured sources.

### Extraction quality, ingestion design and replacement plan (2026-10-13)

Everything below was done locally: no database write, no Pinecone operation, no embedding call, no migration, nothing committed.

**Extraction quality.** `app/services/education_page_extractor.py` (opt-in, Admizz only; the shared `extract_text_from_html` is unchanged and pinned by a test). Checked by reading real pages against their HTML (not by character count) on the UK guide, three dated answer pages, a long article, the 15-scholarships list, the test-prep page and `/register`:
- The shared extractor deletes any element whose class merely contains "ad", "nav", "menu" or "header"; Tailwind's `leading-relaxed` contains "ad". On the UK visa-fee answer page it returned only "Related Articles / Accepting Applications / 24hr Response"; the extractor returns the title and byline, the quick answer, the details, the sources list, the "Checked in October 2026" line and the FAQ (1,304 characters, 2 FAQ items together with their answers).
- Headings stay with their text and every block starts with its heading path ("Frequently Asked Questions › Question"), so a chunk says what it is about. A FAQ question and answer are one block; on the real pages no chunk boundary separates one from the other (checked for every FAQ item on 7 pages).
- On `/test-prep` the FAQ answers are not in the visible HTML at all (collapsed accordion) and the questions sit inside buttons; both are recovered, the answers from the page's own FAQPage JSON-LD, deduplicated by question.
- Left out on purpose: navigation, footers, breadcrumbs, related articles and guides, calls to action, statistics and marketing panels ("2,000+ students", "95% approval"), testimonial and alumni sections, bare step counters. Kept: sources and the checked statement. Outbound source links (GOV.UK, IRCC...) are collected for the manifest and are NOT placed in the text the AI reads.
- Found by checking real pages and now handled: pages render some sections twice (mobile and desktop copies; repeats are kept once), `/register` is a sign-up page (link-only, never ingested), and country guides contain lists of university names (kept, flagged `university_list`, to be reviewed: they are unverified marketing, not records).
- Known limits: accordion titles that sit outside headings (for example the eight "Why our test prep works" feature titles) are dropped with the tab and filter buttons; the extractor is written for this site's structure and says so with warnings (`no_main`, `no_headings`, `thin_content`, `empty`) when a page does not fit. Extraction decides which words are the page's own; it does not verify them.

**Using it without changing other tenants (options).** `IngestionService.ingest_url` calls the crawler and the shared extractor inline and has no hook for another extractor.
- A. Add an optional `extractor` argument to `ingest_url` (default unchanged). Small, but edits the shared path every tenant uses and still goes through the crawler, which has no robots.txt check, pacing or size limit.
- B. (recommended) A separate "prepared pages" entry that takes already extracted text with the canonical `source_url` and `source_title` and reuses `_process_chunks` unchanged. The dry-run script already produces exactly that, with polite fetching. Other tenants cannot be affected. `_process_chunks` already carries `source_url` and `source_title` into both the Postgres row and the Pinecone metadata (pinned by a test with fake clients).
- C. A per-tenant extractor setting. Most flexible, but needs new configuration and, if stored in the database, a migration.
Option B is not implemented as a write path in this task; the planning logic for it is (`app/services/education_ingest_plan.py`, tested against an in-memory fake store).

**The existing `admizz-test` chunks (read-only look; metadata only).** 27 jobs, 27 chunks, one chunk each, 3,358 tokens. Every job is `source_type='text'`; no job and no chunk has a `source_url`; the page title is in the job's `source_filename`. Chunk `vector_id` is `<job id>_0`; the job is the only document identifier. There is no unique key on source or URL. Title matches with the registry: the UK, USA, Australia and Canada guides (Australia's stored title lacks the site suffix). A title match is NOT proof of the same source. No existing chunk matches Germany or any registry article, answer or service page.

**How replacement actually behaves.** The ingestion service is append-only (a new job and new vector ids on every run): ingesting the same page twice stores it twice. Postgres is committed before Pinecone, so a failure in between leaves rows without vectors, never vectors without rows (the project's known orphan problem, fixed that way). Retrieval cannot tell old from new chunks (no active flag). `delete_customer_data` deletes the tenant's whole Pinecone namespace and must never be used for this.

**Migration-free replacement strategy (planned, not run).**
1. Preflight: dry-run report and manifest reviewed; plan checked (approved urls, no duplicate canonical urls, token budget, nothing retired without a confirmed job id).
2. Add each new page as its own job, verify its Postgres rows and vectors match, then continue (idempotent: a page whose canonical url is already stored by a completed job is skipped, so a rerun adds nothing twice; a failed page is cleaned up and the batch stops, and the same command resumes where it stopped).
3. Only after every new page is stored and verified, retire the old jobs the operator confirmed by job id: vectors first (`delete_vectors`), then the job row (its chunks cascade). A failure leaves stale rows, which are harmless and retryable, never orphan vectors. Old chunks are never retired automatically, not even on a title match.
4. Cost of this order: a short period in which an old thin chunk and its new replacement can both be retrieved. The alternative (retire first) risks a period with no answer. Detection of a half-written ingestion: `find_inconsistent_jobs` compares Postgres row counts with vector counts per job (the existing `scripts/vector_reconciliation.py` does this against the live stores).
Rollback is the same retirement step applied to the new job ids (recorded in the run log); nothing in this plan needs a migration. A substantial refactor would only be needed for an "active/version" flag on chunks, which is not required here.

**Manifest summary (final live dry run, 2026-10-13).** 36 registry pages fetched, 0 rejected; 35 eligible; 131 chunks (51,806 tokens) in 2 embedding calls, about $0.0067 under the stated assumption (text-embedding-3-large at about $0.13 per million tokens, batches of 100; check current pricing). Content classes (how a page presents itself; none is verified): 9 `source_backed` (states a checked date and cites an official source), 18 `dated`, 9 `explanatory`. Excluded: `/register` (link-only). Flagged for review before any ingestion: the five country guides (`university_list`; the Australia and Canada guides also repeat sections), and the two service pages (marketing copy). Title-only overlap with 4 existing jobs (UK, USA, Australia, Canada guides). The shared extractor gave 40 chunks for the same 36 pages in the first dry run (mostly navigation and boilerplate, and for the answer pages none of the answer).

**Recommended next step.** See "Prepared-pages write adapter" below.

### AI reads what the student means (flag, off by default; 2026-10-13)

Keyword rules only know some wordings, so a student who words things differently (or writes Nepali) fell through to a generic reply. `app/services/education_understanding.py` adds one small AI call that reads the MEANING of a typed message. It is behind `EDUCATION_AI_UNDERSTANDING` (default false; floor `EDUCATION_UNDERSTANDING_MIN_CONFIDENCE` 0.7; timeout `EDUCATION_UNDERSTANDING_TIMEOUT_S` 4). This replaces the earlier "no AI intent classifier" restriction; it was lifted by the owner for this narrowly constrained form.

**What the AI can and cannot do.** It answers only with fixed choices: a topic from a closed list (card topics, content topics, follow-up, small talk, other), a country that exists in this tenant's catalog (id, label, alias or Nepali name, matched exactly, never a substring), a language label, a confidence, and, only when the student states their OWN scores, an English test and score, a GPA with its scale and a percentage (each range-checked by the same limits as the score extractor). `Understanding` has no free-text field, so nothing the AI writes is ever shown, linked or stored. The student's message goes in as a JSON data value, never into the instructions; only the card on screen and the country in focus are sent with it (never the profile or contact details); the message is never logged; one call is temperature 0 with a small token cap and a cache.

**How the agent uses it** (typed text only; a tap is already a closed id). The country-switch follow-up ("what about Canada?") still decides first, so the AI is not even asked then. Otherwise, if the AI is confident: a card topic for a catalog country builds that card through the existing tool (cost, facts, eligibility, compare with at least two countries, recommend, profile, counselor); a content topic (visa, process, scholarship, test prep, documents, intakes, requirements) is answered from the knowledge base and a page link, and the keyword rules are NOT allowed to turn it into a card (for example, "what is the uk student visa fee" no longer shows the tuition calculator); the AI's topic and country also choose the page link. Own scores it read are saved after validation (the regex reading wins a tie). If the AI is unsure, fails, times out, returns nonsense, or says follow-up, small talk or other, the keyword rules and the refinement resolver decide exactly as before, so a turn is never worse than it was. A "profile" reading of a message that states the student's own scores is treated as no card.

**Real-model check** (gpt-4o-mini, in memory, 20+ varied messages). Understood: romanized Nepali cost, visa, test-prep and scholarship questions, slang ("wanna go canada, whats it like there"), compare, "talk to someone", a Devanagari visa question, and own-score statements ("mero ielts 6.5 aayo"). Weak spots found and fixed: "process" linked a GPA page (now the country guide, which holds the visa-process steps); statements of own scores showed an unrequested profile card; a Devanagari cost question was read with confidence 0.2 (a Nepali reading aid for the catalog's countries and topics was added to the prompt: confidence 0.7 and the country is now matched). Still limited: it is a small model, so unusual or mixed-language messages can come back unsure (then the rules decide); one extra call adds latency and a little cost per typed message; "which country is the cheapest for me" is read as cost without a country and falls to the budget slider; an answer still needs content: the UK process question still gets the honest "I don't have that detail yet" plus the guide link until the pages are ingested.

### Prepared-pages write adapter (prepared and tested, NOT run; 2026-10-13)

Nothing below was executed against a real database, Pinecone, an embedding service or the network. The tests use fake stores, a fake session, fake vector and embedding clients, and block socket connections.

**Files.** `app/services/education_page_dispositions.py` (who may be ingested), `app/services/education_prepared_ingest.py` (plan, preflight, execute, retire: pure logic behind a `PreparedStore` interface, no clients), `app/services/education_prepared_store.py` (`SqlPineconeStore`, the concrete store over the unchanged `IngestionService._process_chunks`), a read-only `VectorStoreService.existing_ids` (a Pinecone fetch by id, the pattern `scripts/vector_orphan_cleanup.py` already uses), `app/data/education_sources/admizz-test.manifest.json` (the reviewed 36-page manifest, unchanged page list, kept as a data snapshot), and the dry-run script, which now records each page's content hash and disposition. The entry point is `run_prepared_ingestion(pages, store, manifest=..., dispositions=..., target=..., mode="dry_run"|"execute", approval=..., resume=...)`; retirement is a separate `retire_confirmed_jobs(...)`. No command, route or script imports the store or calls either function; ordinary tenant ingestion and the shared crawler are unchanged.

**How a page's disposition is decided** (from the manifest alone; nothing is guessed): `excluded` if the pipeline excluded it (for example `/register`, link-only); `undecided` if the manifest lacks a needed field or claims a page is verified; otherwise `review` if the page has no date or official source (explanatory), is a marketing service page, contains a university list, or has an extraction warning, else `ready`. Result on the real manifest: **27 ready** (9 source-backed, 18 dated), **8 for individual review** (the five country guides, test-prep, scholarship-assistance, visa-assistance), **1 excluded** (`/register`), 0 undecided. Ready pages are ordered source-backed first. Five ready pages were published over a year before 2026-10-13 and carry a freshness note (`us-scholarships`, `us-i20`, `ca-ielts`, `ielts-prep`, `application-documents`): they are not blocked, but their dates should be checked. A reviewer can turn a `review` page into `ready` only by naming themselves and giving a reason; nothing else can be overridden. "Ready" is technical readiness: every page stays `verified: false` and none of this is catalog data.

**Identity and idempotency.** The existing pipeline is append-only: a new job and new vector ids on every run, no unique key on the source. The adapter therefore gives each page a deterministic job id, `uuid5(tenant | canonical url | SHA-256 of the extracted text)` (the job table accepts an explicit id, so no migration), which also fixes its vector ids (`<job id>_<n>`). Before writing, it reads the tenant's jobs for the page's canonical url and decides: no job means `new`; the page's own job complete with matching row and vector counts means `already_ingested` (skipped); the page's own job in any other state means `incomplete_own_job`; a job for the same url with a different id (changed content, or a URL-bearing job from elsewhere) means `ambiguous_same_url_different_content`, reported for review, never skipped silently, never touched. The 27 existing chunks have no `source_url`, so they can never be recognised as "the same source"; they appear only as title-only retirement candidates.

**Failure and recovery** (the two stores are not atomic and nothing here claims they are). Each page is written (Postgres rows committed first, then vectors, by the unchanged pipeline) and then verified in both stores. If a write or the verification fails, that page's own job is cleaned up (vectors, then job and rows) and the batch stops; if the cleanup fails too, both errors are reported. A page left half-written by a crash (`incomplete_own_job`) is reported as `needs_recovery` and the batch stops; with `resume=True` the adapter cleans that one job and writes it again. A page that needs review does not stop the others, but the run is then `completed_with_review_items` and cannot authorise any retirement. Old jobs whose rows and vectors disagree are reported, not repaired. A rerun after a stop adds nothing twice and continues where it stopped.

**Execution approval (all required).** A real run is a separate task that must hand in the database session, ingestion service, vector store and target explicitly, create the store with `allow_real_writes=True`, and pass `mode="execute"` with an `ExecutionApproval` that names the approver, the tenant, the exact page ids and the SHA-256 of the manifest (changing any page, size, class or content hash invalidates it). The tenant must be on the allow-list (`admizz-test` only) and the customer record, site id, education type and Pinecone namespace must all agree with the target. Only `ready` pages can be written, each must match its manifest entry (size and, when recorded, content hash), and the token budget and url checks must pass. A dry run (the default) only reads.

**Add, verify, retire.** (1) Dry run and preflight. (2) Add and verify the new pages. (3) Retrieval checks confirm each replacement is found and useful (the check is a hook the real task supplies; here it is tested with fakes only). (4) Only then, for the exact old job ids named in the approval, delete the job's vectors, then its job row. `retire_confirmed_jobs` refuses unless the executed run was `all_verified`, every confirmed id is a retirement candidate whose replacement page is verified, and the retrieval check passes; it never touches any other job and the adapter has no namespace-wide delete. The four old guide jobs (UK, USA, Australia, Canada, by title only) can be retired only after those four guides, which are in review, have been reviewed, ingested and verified. Temporary duplicate-retrieval risk: between steps 2 and 4 an old thin chunk and its replacement can both be retrieved for the same question. It is kept short by retiring right after verification, and watched with the retrieval checks plus the existing admin retrieval statistics endpoint and a few spot-check questions per country.

**Still limited.** The catalog is still a placeholder and website text is unreviewed, however it is classed. Vector verification reads Pinecone right after the write; if Pinecone is briefly behind, a good page can be reported failed, cleaned and retried (safe, but wasteful). `existing_ids` and `SqlPineconeStore` are tested against fakes, not against live services. The real retrieval check is not implemented. The extractor drops accordion titles outside headings. Everything in this section needs a separate explicit approval before any real run.

## Not verified in this assessment
- The full backend test suite, the widget `tsc` and the widget tests.
- Whether the brief's four phrasings resolve to `recommend_country` today.
- Live reproduction of findings 1.1, 1.2, 1.3 and 1.6.
- Whether production `ALLOWED_ORIGINS` is restrictive.
- Whether migration 042 is applied on the shared Supabase.
- Widget behaviour at 390px and 768px.

## Verification for later phases
- `cd backend && .venv311/bin/python -m pytest tests/ -q`: the full suite stays green, and no known-gap tests are removed or weakened.
- `cd widget && npx tsc --noEmit` and the widget tests.
- Manual check at 390px and 768px, using `http://localhost:5173/blocks-preview.html` (cards, committed) or a local, uncommitted copy of the Admizz demo page pointing at `data-site-id="admizz-test"` (it is kept out of the PR because it hard-codes localhost and the placeholder tenant).
