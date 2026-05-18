# Main Session Log — Zunkiree Search (Window B)

A running journal for handing context across Claude Code sessions. Newest entry at the top. Each entry is dated; each closes with a clear "what's next" so a fresh session can pick up without re-discovery.

The **RESUME HERE** anchor at the bottom is the single source of truth for "what should the next session do first."

---

## 2026-05-02 — Phase 3 §6.1 step 8 unblocked (PR #15)

### What I came in to do

Brain folder dropped `PHASE3-FIX-CONNECTOR-NULL-HANDLING-BRIEF.md` into `/Users/sadinshrestha/Projects/sadin-stark-brain/docs/stella+zunkireesearch/`. Phase 3 verification had stalled at step 8 ("verify price-edit propagation via widget query"). Sadin asked the widget "show me linen pants" and got a generic "we don't carry that right now" response — even though Stella stage definitely had Linen Pants @ Rs 2999 with stock.

Root cause (per brain folder's diagnosis on the Stella side): Stella's legacy `/api/sync/products` returns `"in_stock": null` at product level (variants carry the real `available: true`). Zunkiree's connector read it as `bool(p.get("in_stock", True))` — but `dict.get("k", default)` only returns the default when the key is **missing**, not when it's present-with-null. So `bool(None) → False`, every product flagged out-of-stock to the agent, hallucinated "we don't carry that."

Bundled fix #36 (price string→float coercion missing in the same function) into the same PR, since both were in `_product_from_raw` and both were follow-ups from PR #14's cycle.

### Pre-coding verification (§1)

Did the LOCKED-defaults check before writing any code. Findings:

- §1.1 — Confirmed code shape at `agenticom_connector.py:400` matches the buggy form; price pass-through at lines 385–393. Skipped live curl repro (no AGENTICOM_* creds locally; brain folder accepted code-side inspection as sufficient since they'd already validated Stella's wire shape independently).
- §1.2 — `_product_from_raw` has 3 internal callers (`list_products`, `get_product`, `search_products`); zero external callers. Single-point fix covers everything.
- §1.3 — **Counter to brief's locked default raised**: the existing PR #14 regression test (`test_storefront_realtime_coerces_string_price_from_connector`) bypassed `_product_from_raw` by force-mutating `bad_product.price = "3200.00"` after construction. So removing the `tools.py` workaround would make the test FAIL, not pass naturally as the brief assumed. Brain folder reviewed and locked **OPTION 1**: rewrite the test to route through `_product_from_raw`.
- §1.4 — Existing connector test file is `test_backend_connector.py`. New tests slot in there, no new file.
- §1.5 — `git rev-parse origin/stage` matched brief's expected `d483e339` (PR #14 squash). Confirmed clean base.
- §1.6 — Pure-unit pattern matches existing fixture style.

### What I shipped

Single PR — **#15**, branch `fix/connector-null-handling`, base `stage`, squashed at `d75fd0b` on 2026-05-02 15:20 NPT.

Files changed (4):

- `backend/app/services/connectors/agenticom_connector.py` — `_product_from_raw` rewritten with explicit `is None → True` branching for `in_stock` and explicit `float(...)` coercion for `price` (with fallback chain through variants[0].price preserved). Unparseable price values collapse to `None`, not `0.0`, to honor `Optional[float]` and avoid silent mispricing.
- `backend/app/services/tools.py` — Removed the `float(product.price)` try/except workaround from `_storefront_realtime_add_to_cart`. Cart code now trusts the source. Pre-existing `None → 0.0` defensive guard kept (different case, pre-dates this PR, out of scope per brain folder lock).
- `backend/tests/test_backend_connector.py` (+25 lines) — Three new unit tests: null `in_stock` → True, false `in_stock` → False (legitimate out-of-stock path preserved), string `"3200.00"` → 3200.0 float (with `isinstance` check).
- `backend/tests/test_cart_storefront_realtime.py` — Rewrote `test_storefront_realtime_coerces_string_price_from_connector` per OPTION 1: builds a raw Stella-shaped dict with `"price": "3200.00"`, decodes through `_product_from_raw`, then patches the connector mock. Added a sanity `isinstance(decoded.price, float)` assertion at the decode boundary so source-side regressions fail loudly at the right layer instead of opaquely inside the cart.

168/168 backend tests green locally before the PR opened.

### Stage smoke (Sadin-driven UI test, post-merge)

Deploy fired on merge — GH Action `25249023064` succeeded in 1m3s. Confirmed stage health endpoint returned HTTP 200 and widget config endpoint served huba-nepal config correctly.

I did NOT tail backend logs — my SSH key is not on the stage VPS for either `anish@` or `root@94.136.189.213` (both denied). Brain folder claimed `workflow_brain_vs_repo_split.md` memory said I had access; in this Window B install I do not. **Open follow-up**: that memory needs correction.

Sadin drove the UI and pasted 6 screenshots. Verdict from the screenshots:

- **Step 2** ("show me linen pants") — Carousel rendered with 5 products including Linen Pants @ Rs 2,999, Khukuri Leather @ Rs 3,200, Sherpa Beanie @ Rs 950, Mountain Wool Sweater @ Rs 4,500. Both fixes verified in one observation (in_stock not blanket-false; prices render as clean numbers). ✅
- **Step 3** ("show me Khukuri Leather") — Already surfaced in Step 2's carousel. ✅
- **Step 4** (Add Linen Pants size M to cart) — Clean confirmation, cart line "Linen Pants Size: M Qty: 1 Rs 2,999", subtotal Rs 2,999. PR #14 workaround removal didn't break anything; source coercion picked up the slack. ✅
- **Step 5** ("show my cart") — Linen Pants line + numeric Rs 2,999 subtotal. End-to-end COD checkout completed; order ZK-49D241-7045 confirmed. ✅
- **Bonus**: Order arrived at Stella admin (`dev-stella.zunkireelabs.com`) as `AI-20260502-A5B2AB` with subtotal/total Rs 2,999.00 and customer details correct. Outbound connector → Stella path proven healthy.

**Phase 3 §6.1 step 8 officially unblocked.**

### Anomaly flagged (not blocking PR #15)

In Stella's order detail page for `AI-20260502-A5B2AB`, the **line-item price reads Rs 2700.0** while the **subtotal/total reads Rs 2,999.00** — internally inconsistent within the same order page. Cart UI showed Rs 2,999 throughout the user journey.

Hypothesis (untested): the `ConnectorOrderDraft.line_items[].unit_price` may flow from `ConnectorVariant.price` somewhere downstream, which our PR did **NOT** coerce (scope-locked at product-level only per §1.4 lock). If Stella's variant for size M is priced 2700 separately from product.price 2999, the variant-level string price could be flowing through unchanged.

This is **out of scope for PR #15**. Brain folder will log as a separate follow-up (suggested #41) for diagnosis after Path B lands. Possible the Stella admin display is just showing variant.price for the line-item view and we sent 2999 correctly — needs investigation.

### State at end of session

- `origin/stage` and `origin/main` both at `d75fd0b` (PR #15 squash). Main was fast-forwarded.
- `fix/connector-null-handling` branch deleted from origin (post-merge cleanup).
- Local working tree on this Window B install was on `fix/connector-null-handling` at `a473aa2` (the unsquashed local commit). Local has uncommitted `.claude/settings.local.json` and untracked `backend/.venv311/` — both benign per `vps_uncommitted_edits_recurring.md`.
- A `recovery/prod-uncommitted-2026-05-02-pre-pr14-pr15-deploy` branch appeared on origin during this period — separate incident I wasn't part of, worth understanding before next prod-touching work.

### Open follow-ups generated this session

1. **#41 (suggested)** — Stella order line-item shows Rs 2700 vs subtotal Rs 2999. Investigate `ConnectorVariant.price` string pass-through and whether order draft sources unit_price from variant. Diagnose after Path B.
2. **Memory correction** — `workflow_brain_vs_repo_split.md` / SESSION-LOG §2.1 needs a correction: stage VPS SSH access is NOT pre-configured on this Window B install. Brain folder owns this update.
3. **Latent issue** — `tools.py` `if product.price is not None else 0.0` falls back to a fake 0.0 for genuinely missing prices. Pre-dates this PR, kept per scope lock, but a None-priced product reaching cart should probably error or be filtered at source rather than become a "free" item. Future cycle.

### Closed follow-ups

- **#36** — price string→float coercion at connector boundary. Closed by PR #15.
- **#39** — in_stock null-handling causing "we don't carry that" hallucinations. Fixed by PR #15.

---

## 2026-05-18 — RESUME HERE

**Current state**: main = stage = `12d16f7c` (post-PR-#33, `fix(cart): DB as source of truth`). Brain folder has been the source of truth since 2026-05-02; PRs #20 through #33 all shipped — see brain folder Sessions 25-29 for detail.

**What shipped since the last entry here (2026-05-02)**:

- PRs #22, #23, #45/#46, #47/#48, #49, #50, #51 — full IG language / DM chatbot work (2026-05-08 sweep per brain folder)
- PRs #29–#33 — cart persistence, size validation, DM carousel, post-add-to-cart conversion flow, DB-source-of-truth cart fix
- HSTS labels PR (this branch: `chore/hsts-prod-and-stage`, open against `stage`) — adds `Strict-Transport-Security: max-age=31536000` to prod + stage Traefik routers via `docker-compose.yml` only

**Open items**:

- IG QA structured smoke pass (~25 prompts) — still pending Sadin-driven IG session; not blocked on code
- VPS SSH key for stage: NOT on this Window B install (confirmed again 2026-05-02). Do not attempt `ssh anish@94.136.189.213` for stage log-tailing — it will fail. Brain folder owns the memory correction.

**What NOT to do**:

- Do NOT attempt VPS SSH log tailing — key is not on the stage box
- Do NOT merge the HSTS PR yourself — brain folder does the merge + stage→main fast-forward
- Do NOT mock the database in tests — integration tests must hit a real DB
- Do NOT commit `.claude/settings.local.json` or `backend/.venv311/` (recurring local-only artifacts)

**Pre-flight checklist for the next session**:

```bash
git fetch origin --prune
git log --oneline origin/main -n 3
git status
# Expect main tip = 12d16f7c or newer; status = clean tracked files
```

Read brain folder (`/Users/sadinshrestha/Projects/sadin-stark-brain/`) for the latest brief before acting on any new task.

---
