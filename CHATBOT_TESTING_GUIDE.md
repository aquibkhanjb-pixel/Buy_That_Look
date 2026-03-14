# AI Fashion Chatbot — Presentation Testing Guide

> **Purpose:** A step-by-step script to demo every major feature of the chatbot during
> a presentation. Each section lists what to type, what should happen, and what to highlight.

---

## Before You Start — Pre-flight Checklist

- [ ] Backend server running: `conda activate fashion-ai` → `uvicorn app.main:app --reload` (port 8000)
- [ ] Frontend running: `npm run dev` (port 3000)
- [ ] Gemini API key set in `backend/.env` and verified working
- [ ] Serper API key set in `backend/.env`
- [ ] Open browser at `http://localhost:3000`
- [ ] Open browser DevTools → Network tab (optional, to show API calls)
- [ ] Have a fashion image ready to upload (see Feature 5)

**Expected backend startup log:**
```
LLM service ready
LangGraph chat graph compiled successfully
ReAct outfit subgraph compiled successfully
Chat service (LangGraph) initialised
```

---

## Feature 1 — Basic Text Search (new_search intent)

**What to demonstrate:** Core search pipeline — Classify → Extract → Serper web search → Response

**Type:**
```
Show me blue cotton kurtas for men
```

**What should happen:**
- Intent classified as `new_search`
- Features extracted: `{garment: "kurta", color: ["blue"], fabric: "cotton", gender: "men"}`
- 6–10 product cards appear (sourced from Serper / Indian e-commerce sites)
- Bot response is helpful ("I found some great blue cotton kurtas for you!")
- Feature suggestion appended (e.g., "💡 Try specifying: sleeve length or occasion")

**What to highlight:**
- "Notice it understood 'blue cotton kurtas for men' — not just keyword matching, but structured feature extraction via Gemini"
- "Products come from live web search — they're real products available to buy right now"
- "The bot proactively suggests what else to specify to narrow results"

---

## Feature 2 — Query Refinement (refine intent)

**Type (immediately after Feature 1):**
```
Show in white instead, under ₹1500
```

**What should happen:**
- Intent classified as `refine` (NOT new_search — conversation history is used)
- Features updated: color → ["white"], max_price → 1500
- New set of product cards from a fresh Serper search
- Bot acknowledges the change ("Sure! I've updated the colour to white and filtered to your budget")

**What to highlight:**
- "The intent changed from new_search to refine — it knows I'm modifying, not starting fresh"
- "Gender (men) and fabric (cotton) are still remembered even though I didn't mention them"
- "This is FashionFeatures.merge() — new values update, existing values carry forward"

---

## Feature 3 — Category Switch with Memory Reset

**Type (continuing the same chat):**
```
Now show me a ring to match
```

**What should happen:**
- Intent: `new_search` (completely different item)
- **Category switch detected**: kurta-specific attributes reset, gender + budget kept
- Products shown are rings, not kurtas with ring-related filters
- Feature suggestion is ring-specific: "Try specifying: metal (gold/silver) or gemstone type"

**What to highlight:**
- "The bot detected I switched from kurta to ring — product-specific attributes reset"
- "But gender and budget still apply to the ring search"
- "The suggestion adapts to the new garment type — rings get metal/gemstone suggestions"

---

## Feature 4 — Feedback Handling

### 4A — Positive Feedback

**Type:**
```
These look great!
```

**What should happen:**
- Intent: `feedback_positive` → `just_positive`
- No new search triggered
- Bot responds warmly: "Glad you like them! Would you like to see variations?"

**What to highlight:** "No wasted API call when the user is happy — the bot just responds conversationally"

---

### 4B — Negative Feedback with Refinement

**Type:**
```
Not exactly what I was looking for, show something more formal
```

**What should happen:**
- Intent: `feedback_negative` → `wants_refinement`
- Features updated: style → "formal"
- New Serper search runs, new products shown
- Bot is apologetic + solution-focused

**What to highlight:** "Negative feedback re-triggers feature extraction — 'formal' is added to the next search"

---

### 4C — Very Unsatisfied

**Type:**
```
These are completely wrong, nothing is matching what I want
```

**What should happen:**
- Intent: `feedback_negative` → `very_unsatisfied`
- Web search triggers immediately with direct shopping links
- Bot is apologetic, explains the links

**What to highlight:** "When the user is very unhappy, the system escalates to direct platform links: Myntra → Ajio → Amazon → Flipkart → Meesho"

---

## Feature 5 — Image Upload (Google Lens + Visual Search)

**Prepare:** Have any clothing/outfit photo ready

**Upload the image** using the image button in the chat, then type:
```
Find similar products
```

**What should happen:**
- Gemini Vision describes the image: e.g., "Blue ethnic kurta, half sleeves, embroidered neckline"
- Google Lens search fires: image uploaded to catbox.moe → Serper `/lens` → visually identical products
- Visual web search also runs: Gemini description → Serper text search
- Both merged into results — some cards show "🔍 Google Lens" badge, others "🛒 Web Search"

**What to highlight:**
- "Three search threads run in parallel: text search, visual web search, and Google Lens"
- "Google Lens finds products no keyword query would surface — it searches by visual appearance"
- "The source badge on each product card tells you exactly how it was found"

---

## Feature 6 — Marketplace / Platform Routing

**Type:**
```
Find blue kurtas on Flipkart
```

**What should happen:**
- Intent: `marketplace_search` (detected before Gemini even classifies — keyword pre-check)
- Runs through `extract_fashion_features` (handles image context too)
- Flipkart search URL shown **first**, followed by Amazon, Myntra, Ajio
- URL format: `flipkart.com/search?q=blue+kurta`

**What to highlight:**
- "Platform detection happens before Gemini classification — faster and more reliable"
- "The target marketplace URL always appears first in the link list"

**Also test Ajio:**
```
Search for maroon sarees on Ajio
```
→ Should show `ajio.com/search/?text=maroon+sarees` as the first link

---

## Feature 7 — Clarification Flow

**Start a fresh conversation (New Chat)**

**Type (deliberately vague):**
```
Show me something nice
```

**What should happen:**
- Intent: `new_search`
- Garment type missing → ask_clarification fires
- Bot asks ONE question: "What type of clothing are you looking for?"
- No products shown yet

**Type:**
```
A women's kurta for a casual day out under ₹1000
```

**What should happen:**
- Features: `{ garment: "kurta", gender: "women", occasion: "casual", max_price: 1000 }`
- Serper search runs, products shown
- Clarification count resets

**What to highlight:**
- "The system doesn't dump irrelevant results — it asks before showing poor matches"
- "After 2 rounds of clarification, it proceeds regardless and shows the best it has"

---

## Feature 8 — Outfit Completion (ReAct Subgraph)

**First, do a search:**
```
Show me men's blue cotton kurta
```

**Then (once products appear):**
```
What can I pair this with?
```

**What should happen (Turn 1 of outfit completion):**
- Intent: `outfit_completion`
- Bot asks: "What type of item would you like to pair — footwear, jewellery, or dupatta?"

**Type:**
```
Footwear
```

**What should happen (Turn 2 — ReAct fires):**
- ReAct subgraph extracts reference product attributes
- Stylist Gemini call: determines juttis/mojaris for ethnic kurta
- Serper searches for ethnic footwear
- Results evaluated for style/colour match
- If poor → query refined, search runs again (up to 5 iterations)
- Complementary footwear products shown

**What to highlight:**
- "This is a ReAct (Reason + Act) agent — it searches, evaluates, and refines in a loop"
- "It's looking at the first product I was shown and finding items that complement it"
- "The system uses a colour complement table and style map to guide the search"

---

## Feature 9 — Trend Analyzer

**Scroll to the top of the page (above the chat)**

**What to show:**
- 6 trend cards with real current fashion trends
- Each card: trend name, description, badge (🔥 Hot / 📈 Rising / ✨ New), category, example items
- Click "Explore trend →" on any card

**What should happen:**
- The trend's search query is fired directly into the chat assistant
- Products matching that trend appear

**What to highlight:**
- "Trends are fetched live from fashion news via Serper, then structured by Gemini"
- "The 'Explore trend' button fires a pre-crafted search query directly into the chatbot"
- "Results are cached for 1 hour to avoid repeated API calls"
- "Click Refresh to force a fresh fetch"

---

## Feature 10 — Session Memory Persistence

**Type a sequence:**
```
Show me women's formal dresses under ₹2000
```
*(Products appear)*

```
In black
```
*(Gender, price, and formal style all persist — only colour updated)*

```
For beach instead
```
*(Occasion changes to beach, but gender/price still remembered)*

**What to highlight:**
- "FashionFeatures accumulates across the entire conversation"
- "When I say 'in black', it knows to keep women/formal/₹2000 — it's a refinement, not a new search"
- "Session state is maintained server-side for the duration of the conversation"

---

## Feature 11 — Circuit Breaker / API Resilience

> **Note:** Best explained conceptually unless you can simulate quota exhaustion.

**Explain what happens when Gemini API is unavailable:**

1. **Intent classification fails** → keyword-based fallback activates instantly
2. **Feature extraction fails** → raw user message used directly as search query
3. **Response generation fails** → pre-written message: *"My AI service is temporarily unavailable, but here are the best matches I found"*
4. **60-second circuit breaker** → no further Gemini calls until cooldown expires
5. **Serper still runs** → users always get product results, even without AI

**What to highlight:**
- "The system never crashes or shows a blank error screen"
- "Serper runs independently — product discovery always works"

---

## Quick Demo Script (5-minute version)

| Step | Input | Feature Shown |
|------|-------|--------------|
| 1 | `Show me blue cotton kurtas for men` | Basic search, feature extraction, Serper |
| 2 | `In red, under ₹1000` | Refinement, session memory |
| 3 | `Now show me matching rings` | Category switch detection |
| 4 | `Find these on Myntra` | Marketplace routing, direct links |
| 5 | Upload image + `Find similar` | Google Lens + visual search |
| 6 | `What can I pair this with?` | Outfit completion, ReAct agent |
| 7 | Scroll up to Trend Analyzer → click "Explore trend →" | Trend intelligence |

---

## Things That Were Fixed (Good to Mention)

These are real bugs that were identified and resolved — demonstrates production-level thinking:

| Bug | Fix |
|----|-----|
| Flipkart appearing as "brand" filter → 0 results | Marketplace blocklist in feature extraction prompt |
| Google Lens results not showing for ethnic wear | Moved Lens to `web_search` node (was in `search_local_db` which early-returned) |
| Serper Lens returning empty (`visual_matches` key wrong) | Fixed to use `"organic"` key |
| Serper Lens 403 with old API key | New Serper key with Lens plan |
| Image upload failed for Lens (base64 not accepted) | catbox.moe upload → public URL |
| Ajio links returning 0 results | Fixed URL: `/search/?text=` instead of `/s/` |
| Web results empty even when search succeeded | `update_memory` no longer resets output fields |
| Virtual try-on returning 502 | `hf_token=` → `token=` (gradio_client 2.3.0 breaking change) |
| Category switch carrying stale attributes | Category-switch detection resets product-specific attrs |
| 503 errors not caught by circuit breaker | Added "503/UNAVAILABLE" check with 30s backoff |

---

## Common Interview Questions & Answers

**"How does the recommendation get better over time in a session?"**
> Each turn, `FashionFeatures` accumulates. Gender, budget, and style preferences persist. Only when you switch garment types do product-specific attributes reset. By turn 3–4, the Serper query is highly specific, leading to much better results.

**"What's the latency?"**
> One turn takes roughly: 300ms (classify_intent) + 400ms (extract_features) + 2-3s (web_search with Gemini Vision verification) + 400ms (generate_response) = ~3-4 seconds total. The bottleneck is Serper + Gemini Vision thumbnail verification.

**"Why not just use a local product database?"**
> We removed FAISS and CLIP entirely. A local DB gets stale, requires a scraping + embedding pipeline, and is limited to what you scraped. Serper gives real-time results from every major Indian e-commerce site. Google Lens finds visually identical products no keyword query would surface.

**"How does image search work technically?"**
> Three parallel threads: (1) Gemini Vision describes the image → used as Serper text query with thumbnail verification, (2) Image uploaded to catbox.moe → Serper Google Lens → visually identical products, (3) all results merged by URL. Users get both semantically and visually matched results.

**"Why not just use GPT-4 for everything?"**
> Cost and latency. Gemini Flash Lite is fast and cheap for classification/extraction tasks. Serper handles product discovery with no per-result AI cost. We use Gemini Vision only for image uploads and thumbnail verification — not on every single product.
