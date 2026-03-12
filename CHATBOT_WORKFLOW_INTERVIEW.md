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
│  classify_intent    │  ← Gemini reads last message + history
└─────────────────────┘
         │
         │ conditional edge
         ├─ new_search / refine / marketplace_search ──► extract_fashion_features
         ├─ feedback_positive / feedback_negative    ──► handle_feedback
         └─ general                                  ──► generate_response
                                                              │
                  ┌───────────────────────────────────────────┘
                  │
                  ▼
        ┌────────────────────────┐
        │ extract_fashion_features│  ← Gemini: structured JSON extraction
        └────────────────────────┘
                  │
                  │ conditional edge
                  ├─ marketplace_search ──────────────────────► web_search
                  └─ new_search / refine ──► search_local_db
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │ search_local_db │  ← CLIP + FAISS
                                          └────────────────┘
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │ rerank_results  │  ← Gemini scores 0–10
                                          └────────────────┘
                                                   │
                                                   │ quality_router
                                                   ├─ good (score ≥ 6) ──────────► generate_response
                                                   ├─ mediocre (score 3–5) ──────► ask_clarification
                                                   └─ poor / empty ──────────────► web_search
                                                                                        │
handle_feedback ──► wants_refinement / wants_different ──► extract_fashion_features     │
                └─► just_positive ──────────────────────► generate_response             │
                └─► very_unsatisfied ─────────────────────────────────────────► web_search
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
```

---

## Core Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| AI Orchestration | **LangGraph** (StateGraph) | Directed graph, conditional routing between 9 nodes |
| Language Model | **Google Gemini** (gemini-flash-lite) | Intent, feature extraction, re-ranking, response generation |
| Vision Model | **Gemini Vision** (multimodal) | Describe uploaded outfit images |
| Visual Search | **CLIP** (ViT-B/32) + **FAISS** | Image/text → 512-dim embeddings, similarity search |
| Backend | **FastAPI** | REST API, async request handling |
| Frontend | **React + TypeScript** | Chat UI, product card grid |

---

## Node-by-Node Walkthrough

### NODE 1 — `classify_intent`

**What it does:** Reads the latest user message + conversation history and classifies the intent into one of 5 categories.

| Intent | When used |
|--------|-----------|
| `new_search` | User wants to find products: "Show me blue kurtas" |
| `refine` | Modify previous results: "In red instead", "Under ₹500" |
| `feedback_positive` | User liked results: "Love it!", "Great choices" |
| `feedback_negative` | User disliked: "Not what I wanted", "Show something else" |
| `marketplace_search` | Platform-specific: "Show on Flipkart", "Find on Amazon" |
| `general` | Greeting, meta question: "Hi", "What can you do?" |

**Fallback:** If Gemini API is unavailable (quota/503), a keyword-based classifier takes over. This prevents "not from Flipkart" being misclassified as `new_search`.

**Example trace:**
```
User: "Show me maroon silk sarees for wedding"
→ Gemini prompt: "Classify intent: new_search / refine / feedback_* / general"
→ Gemini output: "new_search"
→ State: { intent: "new_search" }
→ Graph routes to: extract_fashion_features
```

---

### NODE 2 — `extract_fashion_features`

**What it does:** Gemini extracts structured outfit attributes from the conversation into a typed schema (`FashionFeatures`). These are then merged with accumulated session preferences.

**FashionFeatures schema:**
```json
{
  "garment_type": "saree",
  "color": ["maroon"],
  "pattern": null,
  "style": "ethnic",
  "fabric": "silk",
  "occasion": "wedding",
  "gender": "women",
  "max_price": null,
  "min_price": null,
  "brand": null,
  "sleeve_type": null,
  "neckline": null
}
```

**Category-switch detection:**
If user switches garment type (e.g., shirt → ring), only gender and budget carry over — colour/pattern/style are reset to avoid contamination.

**Output from this node:**
- **CLIP query:** `"women saree maroon silk ethnic for wedding"` (used for FAISS search)
- **Filters dict:** `{ "max_price": 2000 }` (price/brand only — CLIP handles category semantics)

**Example trace (image upload):**
```
User uploads image of a blue striped shirt + says "find similar"
→ Gemini Vision describes image: "Men's blue striped casual shirt, slim fit, half sleeves"
→ extract_fashion_features merges image description + user message
→ CLIP query: "men shirt blue striped casual slim half sleeves"
→ Graph routes to: search_local_db
```

---

### NODE 3 — `search_local_db`

**What it does:** Converts the CLIP query text into a 512-dimensional embedding using the CLIP ViT-B/32 model, then runs an approximate nearest-neighbour search against the FAISS index.

**How it works:**
1. CLIP encodes the text query → 512-dim vector
2. FAISS `IndexFlatIP` (inner product = cosine similarity for normalized vectors) finds the top-K most similar product embeddings
3. Optional filters applied post-search: price range, brand
4. Minimum similarity threshold: 0.18 (text-to-image cross-modal range)

**Example:**
```
Query: "women saree maroon silk ethnic for wedding"
CLIP → embedding [0.23, -0.11, 0.45, ...]  (512 dims)
FAISS → returns 36 candidates (k*3 for filter headroom)
After price filter → 12 candidates
→ State: { local_results: [12 products with similarity scores] }
```

---

### NODE 4 — `rerank_results`

**What it does:** Sends the 12 FAISS candidates to Gemini for semantic re-scoring on a 0–10 scale. This catches cases where CLIP found visually similar items that aren't what the user asked for.

**Scoring tiers:**
| Score | Category | Action |
|-------|----------|--------|
| ≥ 6 | Top result | Shown prominently |
| 3–5 | Possible match | Shown in "Other" section |
| < 3 | Unrelated | Hidden |

**Quality gate → routing decision:**
| Quality | Condition | Next node |
|---------|-----------|-----------|
| `good` | Best score ≥ 6 OR all scores null (Gemini down) | `generate_response` |
| `mediocre` | Best score 3–5 | `ask_clarification` |
| `poor` | Best score < 3 but results exist | `web_search` |
| `empty` | No results at all | `web_search` |

**Why "all scores null → good"?** When Gemini quota is exhausted, all scores are null. Rather than triggering web search unnecessarily, the system trusts CLIP's similarity ranking and shows results directly.

**Example:**
```
12 saree candidates → Gemini scores them
Top scores: [8, 7, 6, 5, 4, 4, 3, 3, 2, 2, 1, 0]
Best score = 8 → quality = "good"
→ Graph routes to: generate_response
Products with score ≥ 6 shown: [saree-1, saree-2, saree-3]
```

---

### NODE 5 — `ask_clarification`

**What it does:** When results are mediocre (best score 3–5), Gemini generates ONE focused clarifying question instead of showing poor results. Increments `clarification_count`.

**Auto-escalation:** After 2 clarifications, the system stops asking and routes to `web_search` instead.

**Missing field detection order:**
1. Gender
2. Garment type
3. Occasion
4. Budget

**Example:**
```
User: "Show me something nice"
→ FAISS finds 12 products, Gemini scores: best = 4 → quality = "mediocre"
→ clarification_count = 0 (< 2) → ask_clarification
→ Gemini: "What's the occasion — are you looking for something casual or formal?"
→ clarification_count incremented to 1
→ User answers: "For office, formal"
→ Next turn: rerank → best = 8 → quality = "good" → clarification_count reset to 0
```

---

### NODE 6 — `handle_feedback`

**What it does:** When intent is `feedback_positive` or `feedback_negative`, Gemini sub-classifies the feedback into one of 4 actions.

| Feedback Action | Example | Next action |
|----------------|---------|-------------|
| `wants_refinement` | "Show in red instead", "Cheaper please" | Re-extract features + search |
| `wants_different` | "Show me completely different style" | Re-extract features + search |
| `just_positive` | "Love it!", "Perfect, thanks" | Generate warm response, no re-search |
| `very_unsatisfied` | "These are terrible, nothing works" | Force web search |

**Example:**
```
User: "These are nice but show me something cheaper"
→ classify_intent: "feedback_negative"
→ handle_feedback: "wants_refinement"
→ Routes back to extract_fashion_features
→ Features updated: max_price set lower
→ New FAISS search with price filter
```

---

### NODE 7 — `web_search`

**What it does:** Triggered when local DB has no/poor results, user asks for a specific platform, or user is very unsatisfied. Generates direct shopping links to Indian e-commerce platforms.

**Two modes:**

**Mode 1 — General web search (no platform specified):**
1. Gemini generates 3 targeted search queries
2. Tries Gemini Grounding (Google Search tool) for live product URLs
3. Falls back to direct search links if grounding fails

**Mode 2 — Platform-specific (e.g., "find on Flipkart"):**
1. Extracts features first (including any uploaded image description)
2. Skips Gemini Grounding — goes straight to direct links
3. Requested platform shown first, followed by others

**Verified URL formats:**
```
Flipkart:  flipkart.com/search?q={query}
Amazon:    amazon.in/s?k={query}
Myntra:    myntra.com/search?rawQuery={query}
Ajio:      ajio.com/search/?text={query}
Meesho:    meesho.com/search?q={query}
```
All queries are `quote_plus` encoded (spaces → `+`).

**Example trace:**
```
User: "Find blue kurtas on Ajio"
→ classify_intent: marketplace_search (target: "ajio")
→ extract_fashion_features: query = "blue kurta"
→ web_search: skips grounding, builds direct links
→ First link: "Search on Ajio: blue kurta" → ajio.com/search/?text=blue+kurta
→ Plus Amazon, Myntra, Flipkart as alternatives
```

---

### NODE 8 — `generate_response`

**What it does:** Gemini writes a friendly, contextual 2–3 sentence response. The tone adapts to the intent. Product cards are rendered separately by the frontend — the response text does NOT list products.

**Tone guide:**
| Intent | Tone |
|--------|------|
| `new_search` | Excited and helpful |
| `refine` | Acknowledging the change |
| `feedback_positive` | Warm, suggest variations |
| `feedback_negative` | Apologetic, solution-focused |
| `general` | Friendly, conversational |

**Feature suggestion system:** After any search, the bot checks which attributes the user hasn't specified yet and appends a proactive tip:
```
"💡 Want more precise results? Try specifying: fabric (cotton/silk) or sleeve length."
```
This is garment-specific — kurtas suggest fabric/sleeve, rings suggest metal/gemstone.

**Graceful degradation:** If Gemini quota is exhausted and no web search was done, the response is a pre-written fallback with the CLIP results shown directly.

**Example:**
```
Found 3 maroon silk sarees (scores: 8, 7, 6)
→ Gemini response: "I found some beautiful maroon silk sarees perfect for a wedding!
   These have rich textures and elegant drapes. 🛍️

   💡 Want more precise results? Try specifying: embroidery style or price range."
→ 3 product cards shown in UI
```

---

### NODE 9 — `update_memory`

**What it does:** Maintains the rolling conversation window and persists session preferences.

**Actions:**
1. Appends assistant reply to message history
2. Trims messages to last 20 (10 user + 10 assistant turns)
3. Resets clarification count if quality was "good" this turn
4. Clears intermediate search state (local_results, final_results)
5. Persists `user_preferences` (FashionFeatures) and `clarification_count` for next turn

**Important:** Output fields (`web_results`, `products_to_show`, `response`, `intent`) are NOT reset here — they are read by `ChatService.invoke()` after the graph finishes.

---

## End-to-End Example: Full Session

**Scenario: User finds a wedding kurta, then wants a matching ring**

```
Turn 1:
User: "Show me embroidered kurtas for wedding"
  classify_intent        → new_search
  extract_features       → {garment: "kurta", pattern: "embroidered", occasion: "wedding"}
  search_local_db        → 12 kurta candidates
  rerank_results         → best = 8, quality = "good"
  generate_response      → "Found some beautiful embroidered kurtas for your wedding!"
  update_memory          → saves {garment: "kurta", occasion: "wedding"}

Turn 2:
User: "Show me a ring to match"
  classify_intent        → new_search
  extract_features       → new_garment = "ring", old_garment = "kurta"
                           *** CATEGORY SWITCH DETECTED ***
                           → Resets: color, pattern, style, fabric
                           → Keeps: gender, budget
                           → Current features: {garment: "ring"}
  search_local_db        → 12 ring candidates
  rerank_results         → best = 7, quality = "good"
  generate_response      → "Here are some elegant rings that would complement your look!"
                           "💡 Want more precise results? Try specifying: metal (gold/silver/rose gold) or occasion (casual/wedding)."

Turn 3:
User: "Show them on Myntra"
  classify_intent        → marketplace_search (target: "myntra")
  extract_features       → preserves {garment: "ring"} context
  web_search             → myntra.com/search?rawQuery=ring + Amazon, Ajio, Flipkart links
  generate_response      → "Here are direct links to search for rings on Myntra and other platforms!"
```

---

## Key Design Decisions (Frequently Asked)

**Q: Why LangGraph instead of a simple if-else chain?**
> LangGraph gives us a declarative, visual graph structure. Each node is testable independently. Conditional edges make routing logic explicit. When we add new nodes (e.g., outfit_complete_the_look), we just add them to the graph — no refactoring needed.

**Q: Why CLIP + FAISS instead of text search (Elasticsearch)?**
> CLIP understands visual-semantic relationships. "Flowy beach dress" finds similar products even if those exact words aren't in the product title. FAISS provides sub-millisecond similarity search across 50k+ products.

**Q: Why use Gemini for re-ranking after CLIP search?**
> CLIP is good at visual similarity but can return items that look alike but are contextually wrong. Example: A search for "formal office shirt" might return "casual printed shirt" because they're visually similar. Gemini re-ranks by semantic relevance, catching these mismatches.

**Q: What happens when Gemini API quota is exhausted?**
> A circuit breaker activates for 60 seconds. During this window: intent uses keyword fallback, features return empty (CLIP query from raw message), re-ranking marks all scores as null (triggers "good" quality to show CLIP results directly), and response generation uses a pre-written fallback message. The system degrades gracefully without returning random products.

**Q: How does session memory work?**
> The `FashionFeatures` object accumulates across turns on the server (in `_sessions` dict keyed by conversation_id). The frontend mirrors it and sends it back in each request as a safety net. On category switch, product-specific attributes reset but gender/budget persist.

---

## Plain English Explanation (For Interviews)

When a user sends a message, the chatbot does not treat it as a standalone command — it reads the entire conversation history and figures out what the user is actually trying to do. This first step is called intent classification. If the user is searching for something new, the system goes into search mode. If they are refining a previous result, it updates the existing search. If they are expressing happiness or frustration, it handles that as feedback. This routing decision is what makes the bot feel intelligent rather than robotic, because the same words like "show me something else" are understood differently depending on context.

Once the system knows the user wants to search, it extracts structured information from the message — things like garment type, colour, fabric, occasion, and price. These are merged with everything the user has already told the bot in the same session. So if the user said "women's" two messages ago, the bot still remembers that and applies it to the new search. This structured description is then converted into a 512-dimensional vector using CLIP, a model that understands both images and text in the same space. FAISS, a high-speed similarity search library, then scans through the entire product catalogue in milliseconds and returns the closest matches. After that, Gemini scores each result for relevance from 0 to 10 and sorts them — this second pass catches cases where visually similar items are not actually what the user asked for.

Finally, if the local database does not have good enough results, the system automatically escalates. It may ask the user one clarifying question to narrow the search, or it may switch entirely to generating direct shopping links for platforms like Flipkart, Amazon, Myntra, and Ajio. If the user uploads an image, Gemini Vision describes the clothing in detail, and that description becomes the search query — connecting the image world to the text-based search engine. The whole pipeline is designed so that every failure has a fallback: if Gemini is down, keyword rules take over; if the database has nothing, the web links kick in; if results are poor, the bot asks rather than guessing. The goal is that the user always gets something useful, no matter what.
