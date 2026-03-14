# AI Fashion Chatbot — Interview Workflow Walkthrough

> **How to use this doc:** Walk the interviewer through the system diagram first, then trace
> through each example scenario node-by-node. Use the architecture diagram as your visual aid.

---

## System Architecture (LangGraph StateGraph)

```
START
  │
  ▼
┌─────────────────────┐
│  classify_intent    │  ← Gemini reads last message + history (10-turn window)
└─────────────────────┘         └─ keyword fallback if Gemini unavailable
         │
         │ conditional edge
         ├─ new_search / refine / marketplace_search ──► extract_fashion_features
         ├─ outfit_completion ────────────────────────► outfit_completion_node
         ├─ feedback_positive / feedback_negative    ──► handle_feedback_node
         └─ general                                  ──► generate_response
                  │
                  ▼
        ┌────────────────────────┐
        │ extract_fashion_features│  ← Gemini: structured JSON extraction
        └────────────────────────┘    FashionFeatures.merge() preserves cross-turn memory
                  │
                  │ conditional edge
                  ├─ garment missing? ──────────────► ask_clarification (max 2x)
                  └─ complete ─────────────────────► web_search
                                                          │
                                              ┌───────────┼───────────┐
                                              ▼           ▼           ▼
                                       Serper text   visual web   Google Lens
                                        search        search       search
                                       (always)     (if image)   (if image)
                                              │           │           │
                                              └───────────┴───────────┘
                                                          │
                                                    merge + dedup by URL
                                                          │
                                                          ▼
                                                ┌──────────────────┐
                                                │ generate_response │  ← Gemini
                                                └──────────────────┘
                                                          │
                                                          ▼
                                                ┌──────────────────┐
                                                │  update_memory    │  ← trim to 10 turns
                                                └──────────────────┘
                                                          │
                                                         END

handle_feedback_node:
  wants_refinement / wants_different ──► extract_fashion_features
  just_positive ───────────────────────► generate_response
  very_unsatisfied ────────────────────► web_search

outfit_completion_node:
  turn 1: asks clarifying question ────► update_memory (END)
  turn 2: invokes ReAct subgraph ──────► update_memory (END)
```

---

## Core Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| AI Orchestration | **LangGraph** (StateGraph) | Directed graph, conditional routing between 8 nodes |
| Language Model | **Google Gemini** (gemini-flash-lite-latest) | Intent, feature extraction, re-ranking, response generation |
| Vision Model | **Gemini Vision** (multimodal) | Describe uploaded outfit images, verify search thumbnails |
| Product Search | **Serper.dev** (Shopping + Lens) | Real-time web search + Google Lens visual matching |
| Image Hosting | **catbox.moe** | Public URL for Google Lens (Serper Lens needs URL, not base64) |
| Backend | **FastAPI** | REST API, async request handling, multipart/form-data |
| Frontend | **Next.js + TypeScript** | Chat UI, trend cards, product card grid |

---

## Node-by-Node Walkthrough

### NODE 1 — `classify_intent`

**What it does:** Reads the latest user message + conversation history and classifies the intent.

| Intent | When used |
|--------|-----------|
| `new_search` | User wants to find products: "Show me blue kurtas" |
| `refine` | Modify previous results: "In red instead", "Under ₹500" |
| `marketplace_search` | Platform-specific: "Show on Flipkart", "Find on Amazon" |
| `outfit_completion` | "What goes with this?", "What can I pair this with?" |
| `feedback_positive` | User liked results: "Love it!", "Great choices" |
| `feedback_negative` | User disliked: "Not what I wanted", "Show something else" |
| `general` | Greeting, meta question: "Hi", "What can you do?" |

**Fallback:** If Gemini API is unavailable (quota/503), a keyword-based classifier takes over instantly. This prevents "not from Flipkart" being misclassified as `new_search`.

**Example trace:**
```
User: "Show me maroon silk sarees for wedding"
→ Intent: new_search
→ Proceeds to: extract_fashion_features
```

---

### NODE 2 — `extract_fashion_features`

**What it does:** Calls Gemini to extract a structured `FashionFeatures` object from the conversation.

**Input:** Full conversation history + latest message
**Output:** Structured JSON merged into existing FashionFeatures

**Example:**
```
User: "I want something flowy for Goa trip, like a boho vibe, under ₹1500"

FashionFeatures extracted:
{
  "garment_type": "dress",
  "style": "boho",
  "occasion": "beach",
  "max_price": 1500,
  "gender": "women"   ← inferred from context
}

Structured query: "women boho beach dress relaxed under ₹1500"
```

**Category switch detection:**
If garment_type changes (e.g., kurta → ring):
- Reset: color, style, fabric, fit, pattern (product-specific)
- Keep: gender, max_price (user-level preferences)

**Platform detection:**
`_detect_marketplace()` runs before Gemini — if "Flipkart/Amazon/Myntra" is in the message, `marketplace_search` intent is set. The platform's URL is shown first in search results.

---

### NODE 3 — `web_search`

**What it does:** The ONLY search node. Runs three parallel threads and merges all results.

**Thread 1 — Serper text search (always runs):**
- Builds structured query: `"women boho beach dress Myntra Ajio"`
- Calls Serper Shopping API
- Gemini Vision verifies product thumbnails (match/reject)
- Falls back to raw results if Vision unavailable

**Thread 2 — Visual web search (image uploads only):**
- Gemini Vision describes the uploaded image
- Description used as Serper text query
- Gemini Vision verifies results against original image

**Thread 3 — Google Lens (image uploads only):**
- Upload image to catbox.moe → public URL
- Serper `/lens` endpoint → `"organic"` key in response
- Returns visually identical products from across the internet

**All three results merged + deduplicated by URL.**

**Fallback if all fail:** Direct search links to Myntra → Ajio → Amazon → Flipkart → Meesho

**Example trace:**
```
User: [uploads photo of red lehenga] "Find similar"
Thread 1: Serper text → "red lehenga bridal women India" → 8 verified products
Thread 2: Gemini Vision → "red silk lehenga embroidered" → Serper → 5 products
Thread 3: catbox.moe → Serper Lens → 12 visually identical results
Merged: 18 unique products (deduplicated by URL)
```

---

### NODE 4 — `generate_response`

**What it does:** Gemini generates a warm, conversational reply explaining the results.

- References specific products found
- Explains why they match the user's request
- Appends a feature suggestion: "💡 Try specifying: sleeve length or occasion"
  - Rule-based (no extra API call)
  - Garment-specific: rings suggest metal/gemstone, kurtas suggest fabric/sleeve

**Circuit breaker response:**
If Gemini is unavailable, returns: *"My AI service is temporarily unavailable. Here are the best matches I found:"*

---

### NODE 5 — `ask_clarification`

**What it does:** Asks ONE focused question when garment type is missing.

- Fires at most **2 times** per conversation (tracked in session)
- After 2 clarifications → proceeds directly to web_search
- Always ONE question: "What type of clothing?" before "What occasion?"

---

### NODE 6 — `handle_feedback_node`

**What it does:** Routes feedback into appropriate follow-up actions.

| Sub-intent | Action |
|-----------|--------|
| `wants_refinement` | Extract new features → web_search |
| `wants_different` | Reset style/color, extract → web_search |
| `just_positive` | Warm reply, suggest next steps |
| `very_unsatisfied` | Skip to web_search immediately |

---

### NODE 7 — `outfit_completion_node`

**What it does:** Finds complementary items for a shown product using ReAct.

- **Turn 1:** Asks clarifying question ("What type of item to pair?")
- **Turn 2:** Invokes 5-node ReAct subgraph (searches online, evaluates style match, loops up to 5x)
- Routes directly to `update_memory` (bypasses `generate_response`)

**ReAct subgraph nodes:**
1. `oa_extract_attributes` — color/style/occasion from reference product
2. `oa_style_coordinate` — Gemini "fashion stylist" call → ideal complement + colour palette
3. `oa_generate_query` — Iter 0: stylist's query; Iter 1: alt query; Iter 2+: Gemini refines
4. `oa_search_web` — Serper search for complementary items
5. `oa_evaluate_results` — Check category + style/color vs ideal_style + color_palette
6. `oa_format_response` — Final response (apologetic if 5 iterations reached)

---

### NODE 8 — `update_memory`

**What it does:** Persists session state across turns.

- Trims conversation to 10 turns (rolling window)
- Does NOT reset output fields (`web_results`, `products_to_show`) — these are reset in `initial_state` instead
- Persists: `last_shown_product`, `disliked_features`, `last_search_query`, `awaiting_outfit_detail`

---

## Example End-to-End Trace

**User:** "Show me blue cotton kurtas for men under ₹1200"

```
classify_intent → new_search
extract_fashion_features:
  { garment: "kurta", color: ["blue"], fabric: "cotton", gender: "men", max_price: 1200 }
  query: "men blue cotton kurta under ₹1200"
web_search:
  Thread 1: Serper → 10 products verified by Gemini Vision
  Thread 2: no image, skipped
  Thread 3: no image, skipped
  Result: 10 unique products
generate_response:
  "Found 10 great blue cotton kurtas for you! Here are the top picks..."
  + "💡 Try specifying: sleeve type or occasion for more precise results"
update_memory:
  session["last_shown"] = ["Men's Blue Cotton Kurta...", ...]
  conversation trimmed to 10 turns
```

**User (next turn):** "In white instead, budget same"

```
classify_intent → refine
extract_fashion_features:
  merge: { garment: "kurta", color: ["white"], fabric: "cotton", gender: "men", max_price: 1200 }
  ← color updated; garment/gender/price/fabric carried forward
web_search:
  Thread 1: Serper → "men white cotton kurta under ₹1200" → 8 products
  ...
```

---

## Common Interview Questions

**"Why use Serper.dev instead of a local product database?"**
> A local database gets stale, requires a scraping + embedding pipeline, and is limited to whatever you scraped. Serper gives real-time product discovery from every major Indian e-commerce site. Google Lens finds visually identical products that no keyword query would surface. The quality and freshness is far superior.

**"What's the latency?"**
> classify_intent (~300ms) + extract_features (~400ms) + web_search (~2-3s) + generate_response (~500ms) = ~3-4 seconds total. The bottleneck is Serper response time + Gemini Vision thumbnail verification.

**"What happens when Gemini is down?"**
> Two-layer resilience: (1) keyword-based intent fallback activates instantly, (2) Serper search still runs without Gemini. The response uses a pre-written fallback message. A circuit breaker prevents hammering a down API — 60s cooldown for quota, 30s for service errors.

**"How does Google Lens work in your system?"**
> The user's image needs a public HTTPS URL (Serper Lens doesn't accept base64). We upload it to catbox.moe (free, no auth) to get a URL, then POST to Serper's `/lens` endpoint. Results come back under the `"organic"` key and contain real product matches from Google's image index.

**"How does memory work across turns?"**
> `FashionFeatures.merge()` accumulates attributes across turns, never overwriting existing values with None. So "Show me women's kurtas" in turn 1 → gender persists through all subsequent turns. When garment type changes, only product-specific attributes (color, style, fabric) reset — user-level preferences (gender, budget) are kept.
