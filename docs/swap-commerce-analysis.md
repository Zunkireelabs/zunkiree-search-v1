# Swap Commerce — Competitive Analysis

**Source:** Screen recording of swap-commerce.com demo (Studio Nicholson store)
**Date:** 2026-03-15
**Duration:** 20 seconds

---

## Demo Flow Timeline Time | What Happens |
|------|-------------|
| 0–2s | Homepage demo widget. AI describes coats with rich detail — Haver Coat (technical trench, detachable shoulder panel), Ria Coat (fluid A-line, dense Melton wool), Hollis (water-repellent cotton-nylon), Mackintosh (handcrafted, fully waterproof). Shows **product cards** with images + prices (£950, £795). Asks preference: "tailored or relaxed drape?" |
| 2–4s | User asks: **"Which size do you recommend for the Ria coat. I am 5'5" in height"**. AI gives personalized sizing: "At 5'5", you're petite relative to our model sizing (Ria shown on someone 5'10"). Given the Ria is designed to be oversized, we'd suggest UK4 or UK6 for balanced proportion." Asks follow-up about usual tailoring size. |
| 4–8s | Page reloads. User types: **"Looking for some outerwear for the weekend — any structured coats or jackets?"** |
| 8–12s | AI responds with detailed product descriptions for structured options. Shows product cards inline with images. |
| 12–16s | User types **"UK6"**. AI responds: **"Done. The Ria Coat in Dark Navy, UK6 is in your bag. Subtotal is £795."** Asks: "Ready to checkout, or would you like to browse further?" |
| 16–18s | User types **"Check out please!"** |
| 18–20s | Widget resets to new session. |

---

## Key Features

### 1. Conversational Product Discovery
- AI doesn't just list products — it **describes them with rich detail** (fabric, silhouette, construction)
- Uses fashion-specific language: "fluid A-line silhouette", "dense Melton wool", "detachable shoulder panel"
- Asks clarifying preference questions: "tailored or relaxed drape?"

### 2. Product Cards with Images
- Side-by-side product cards inline in chat
- Each card: product image, name, price
- Bookmark/save icon on each card

### 3. Personalized Sizing Advice
- AI knows model dimensions (model shown is 5'10")
- Recommends sizes based on user's height (5'5" → UK4 or UK6)
- Understands oversized vs fitted design intent
- Asks follow-up: "What's your usual size in tailoring or trousers?"

### 4. Natural Language Cart
- No button clicks needed — user just says "UK6" and it's added
- AI confirms: "Done. The Ria Coat in Dark Navy, UK6 is in your bag. Subtotal is £795."
- Conversational flow, not form-filling

### 5. Conversational Checkout
- "Check out please!" triggers checkout
- No separate checkout page within the widget

---

## Gap Analysis: Zunkiree vs Swap

| Feature | Swap Commerce | Zunkiree Search | Gap |
|---------|--------------|-----------------|-----|
| Product cards with images | ✅ Rich cards | ✅ Implemented | — |
| Conversational product discovery | ✅ Rich descriptions | ⚠️ Basic descriptions | Need richer product data |
| Personalized sizing advice | ✅ Model dims, body-type aware | ❌ None | Need product detail scraping |
| Fabric/material knowledge | ✅ Knows materials per product | ❌ Not scraped | Need to scrape product details |
| Natural language cart | ✅ "UK6" adds to cart | ✅ Agent supports this | — |
| Direct REST cart | Unknown | ✅ Implemented (v2) | Ahead |
| Conversational checkout | ✅ | ✅ | — |
| Bookmark/save on cards | ✅ | ❌ | Nice-to-have |
| Shadow DOM isolation | Unknown | ✅ Implemented (v2) | Ahead |
| Product search API | Unknown | ✅ Implemented (v2) | Ahead |

### Priority Gaps to Close

1. **Rich product descriptions** — Scrape full product detail pages (fabric, fit, care, model measurements)
2. **Sizing intelligence** — Extract size guides, model dimensions, fit type (oversized/fitted)
3. **Fashion-aware prompting** — Update agent system prompt with fashion vocabulary and styling advice capabilities

---

## Implementation Plan

### Phase 1: Richer Product Scraping
- Scrape full product description text (not just meta description)
- Extract fabric/material composition
- Extract care instructions
- Extract fit type (oversized, slim, regular)
- Extract model measurements if available (height, size worn)

### Phase 2: Size Guide Extraction
- Scrape size guide tables from product pages
- Store as structured data per product
- Make available to the agent via tool results

### Phase 3: Agent Prompt Enhancement
- Add fashion-specific system prompt instructions
- Enable personalized sizing recommendations
- Train conversational style to match Swap's advisory tone
