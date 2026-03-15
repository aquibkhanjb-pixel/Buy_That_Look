# Fashion Recommendation System — Project Explanation

## Problem Statement

Online fashion shopping is overwhelming. A user might see an outfit on Instagram, at a party, or on the street and think — "I want something like that." But finding it online requires manually browsing thousands of products across different e-commerce sites. Traditional keyword search fails when you have a visual idea but no words for it.

Even when users can describe what they want, real conversations don't look like search queries. "Something boho for a Goa trip, not too expensive, nothing floral" — a keyword engine can't process that. It needs a fashion brain.

**The core problem**: There is no easy way to shop for fashion the way people naturally think — conversationally, visually, and contextually.

---

## How Our System Solves It

We built an **AI-powered fashion stylist** with four main capabilities:

1. **Conversational Search** — Chat naturally with an AI assistant. It understands intent, extracts structured fashion attributes, searches the web for real products, and remembers your preferences across the conversation.
2. **Image-Based Discovery** — Upload any outfit photo and the system uses Google Lens to find visually identical or similar products from live e-commerce sites.
3. **Outfit Completion** — Ask "what goes with this?" and a ReAct reasoning agent searches for complementary items, coordinating colour palettes and styles.
4. **Trend Intelligence** — A Trend Analyzer fetches real fashion news from the web and uses Gemini to extract the top 6 current trends with direct "explore" buttons.

Bonus: **Virtual Try-On** — Try any product on your own photo using a diffusion model running on HuggingFace.

---

## System Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js 14)                      │
│  Trend Cards  │  AI Chat Assistant  │  Virtual Try-On Modal  │
└────────────────────────┬─────────────────────────────────────┘
                         │ REST API
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                  Backend (FastAPI / Python)                   │
│                                                              │
│  LangGraph StateGraph ──► Google Gemini (gemini-flash-lite)  │
│  Serper.dev  ──► Product search + Google Lens + News         │
│  HuggingFace ──► IDM-VTON diffusion model (try-on)          │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
              PostgreSQL + Redis (cache) + catbox.moe (image hosting)
```

---

## Detailed Workflow

### Step 1: User Sends a Message

The user types in the chat. They may also attach an image. The message hits `POST /api/v1/chat/` as multipart/form-data.

### Step 2: LangGraph Routes the Request

The backend runs a **LangGraph StateGraph** — a directed graph of AI nodes with conditional routing. Every message flows through this graph:

```
classify_intent
    │
    ├─ new_search / refine / marketplace ──► extract_fashion_features ──► web_search
    ├─ outfit_completion ──────────────────► outfit_completion_node (ReAct subgraph)
    ├─ feedback ───────────────────────────► handle_feedback
    └─ general ────────────────────────────► generate_response
```

LangGraph makes the pipeline **auditable and debuggable** — each node is a pure function, routing is explicit, and state is typed with Pydantic.

### Step 3: Intent Classification

`classify_intent` — Gemini reads the user message + last 10 turns of conversation and returns one of:

| Intent | Example |
|--------|---------|
| `new_search` | "Show me blue cotton kurtas for men" |
| `refine` | "In red instead, under ₹1500" |
| `marketplace_search` | "Find these on Flipkart" |
| `outfit_completion` | "What can I pair this with?" |
| `feedback_positive` | "Love it!" |
| `feedback_negative` | "Not what I wanted, show something else" |
| `general` | "Hi, what can you help with?" |

If Gemini is unavailable, a **keyword fallback** takes over instantly — no crashes.

### Step 4: Feature Extraction

`extract_fashion_features` — Gemini reads the conversation and extracts a structured `FashionFeatures` object:

**User says:** "I need something for my cousin's sangeet, not too expensive, boho vibe"

**Gemini extracts:**
```json
{
  "garment_type": "dress",
  "style": "boho",
  "occasion": "wedding",
  "max_price": 2000,
  "gender": "women"
}
```

This structured representation is **much better** than passing raw conversational text to a search engine. Features persist across turns — if you said "women's" in turn 1, you don't repeat it in turn 5.

**Category switch detection:** If you go from searching kurtas to rings, product-specific attributes reset. Only gender and budget carry over.

### Step 5: Web Search (The Only Search)

`web_search` runs **three parallel threads**:

1. **Serper text search** — Structured query (e.g., "women boho wedding dress under ₹2000") sent to Serper Shopping API. Gemini Vision verifies product thumbnails match the intent.
2. **Visual web search** (if image uploaded) — Uses Gemini Vision's description of the image as a Serper text query. Verifies results visually.
3. **Google Lens** (if image uploaded) — Uploads image to catbox.moe for a public URL → Serper `/lens` endpoint → returns visually identical products from across the web.

All three results merge and deduplicate by URL. If all fail, direct search links to Myntra → Ajio → Amazon → Flipkart → Meesho are provided.

### Step 6: Response Generation

`generate_response` — Gemini writes a warm, conversational reply explaining the results. It also appends a smart feature suggestion ("💡 Try specifying: sleeve length or occasion") using a rule-based system — no extra API call.

### Step 7: Memory Update

`update_memory` — Trims conversation to 10 turns. Session memory (gender, budget, style preferences, last shown product) persists across the conversation.

---

## Outfit Completion — ReAct Agent

When the user asks "what goes with this?", a **5-node ReAct subgraph** runs:

1. Extract attributes from the reference product (colour, style, occasion)
2. A "fashion stylist" Gemini call determines the ideal complement, colour palette, and search queries
3. Search Serper for complementary items
4. Gemini evaluates: do these items actually match the style and colour palette?
5. If poor match → refine query and try again (up to 5 iterations)
6. Format final response

This is **Retrieval-Augmented Generation + Tool Use + Reasoning** in one subgraph.

---

## Trend Analyzer

```
Serper /news ("fashion trends India 2026")
    ↓ (live web results)
Gemini extracts 6 structured TrendItem objects
    {name, description, category, badge, search_query, example_items}
    ↓
1-hour in-memory cache
    ↓
Rendered as horizontal scroll of 6 cards
    ↓
"Explore trend →" fires the search_query directly into the chat assistant
```

---

## Virtual Try-On

```
User photo + garment image
    ↓
POST /api/v1/tryon/
    ↓
gradio_client → yisol/IDM-VTON (HuggingFace diffusion model)
    ↓ (~40 seconds)
Side-by-side before/after result shown in modal
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS | SSR, strong typing, utility-first styling |
| **UI Design** | Cormorant Garamond + DM Sans, ivory/noir/gold palette | Editorial fashion aesthetic |
| **Backend** | FastAPI (Python 3.10) | Async, Pydantic validation, automatic Swagger docs |
| **AI Orchestration** | LangGraph (StateGraph) | Explicit, auditable routing between AI nodes |
| **Language Model** | Google Gemini (gemini-flash-lite-latest) | Intent, feature extraction, vision, response generation |
| **Product Search** | Serper.dev (Shopping + Lens + News) | Real-time web search without scraping infrastructure |
| **Virtual Try-On** | yisol/IDM-VTON (HuggingFace) | Diffusion-based garment fitting |
| **Database** | PostgreSQL + SQLAlchemy | Product metadata storage |
| **Cache** | Redis | Result caching |

---

## Key Design Decisions

### 1. No Local Product Database for Search
We removed FAISS vector search and CLIP embeddings entirely. Instead, all product discovery goes through Serper.dev (web search + Google Lens). Benefits:
- Products are always fresh — no stale database
- No embedding pipeline to maintain
- Google Lens finds products that no keyword query would surface
- System works for any garment type worldwide

### 2. LangGraph Over Custom Routing Code
The pipeline has 8+ nodes with complex conditional routing. LangGraph makes each node a pure function and routing a first-class concern — easy to add new nodes, trace execution, and debug failures.

### 3. Parallel Search Threads
Text search + visual web + Google Lens all run concurrently inside `web_search`. Total latency is the slowest thread (~3–5s), not the sum of all three (~10s+).

### 4. Resilience by Design
- **Circuit breaker**: 60s cooldown for Gemini 429 quota; 30s for 503 errors
- **Keyword fallback**: intent classification still works without Gemini
- **Graceful degradation**: Serper runs independently; users always get search links even if AI fails

### 5. Session Memory Without a Database
FashionFeatures accumulate across turns in server-side session state. `merge()` never overwrites with None — critical for multi-turn refinement without re-stating preferences every message.

---

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/chat/` | Main chat (multipart, supports image) |
| `GET /api/v1/trends/` | 6 current fashion trends (1hr cache) |
| `POST /api/v1/tryon/` | Virtual try-on |
| `GET /api/v1/health` | Health check |

---

## Challenges Faced & How I Solved Them

### 1. Google Lens Requires a Public URL
Serper's `/lens` endpoint does not accept base64 — it needs a public HTTPS image URL. **Solution**: Upload images to catbox.moe (free, no authentication) to get a public URL before calling Serper.

### 2. Google Lens Results Had Wrong Key
Initial integration returned empty results. The Serper Lens response uses the `"organic"` key, not `"visual_matches"`. **Fix**: `data.get("organic") or data.get("visual_matches") or []`.

### 3. Gemini Quota Causing Incorrect Routing
When Gemini was unavailable, all intents defaulted to `new_search`, causing stale attributes to be used. **Fix**: Keyword-based intent fallback that correctly handles "not from Flipkart" → `feedback_negative`, etc.

### 4. Category Switch with Stale Attributes
After searching shirts (blue/casual), asking for rings used all shirt attributes in the ring query. **Fix**: Detect garment_type change → reset product-specific attributes, keep gender + budget.

### 5. Platform Detection Treated as Brand Filter
"From Flipkart" → Gemini extracted `brand: "flipkart"` → 0 results. **Fix**: `_MARKETPLACES` blocklist in feature extraction prompt; platforms stripped from brand field.

### 6. Virtual Try-On Returning 502
gradio_client 2.3.0 changed constructor signature from `hf_token=` to `token=`. **Fix**: Updated constructor call.





Tier 1 — High Impact, Feasible

  1. Persistent Wardrobe / Wishlist
  - User saves products they like → "My Wardrobe" tab
  - Next session: "Based on what you saved, here's what pairs well with it"
  - This creates lock-in — they won't leave because their data is here
  - Needs: simple user auth + DB (just a user table + saved_items table)

  2. "Style Profile" Onboarding
  - First visit: 5-question quiz (body type, style vibe, budget, occasions, favorite colors)
  - Every search is personalized from day 1
  - Users feel understood immediately
  - This is the #1 reason people pay for styling apps (Stitch Fix charges $20/month just for this)

  3. Complete the Look — Shown Automatically
  - When chat returns products, automatically show: "Complete this look →" button
  - Currently outfit completion is a separate manual request
  - Make it a one-click action on every product card
  - High engagement, drives more Serper queries (which you're already paying for anyway)

  4. Price Drop Alerts
  - User saves a product → you check price daily → notify by email when price drops
  - Needs: a simple cron job + email (Resend.com free tier = 3k emails/mo)
  - This alone can justify a ₹99/mo subscription — Amazon does this and users love it

  ---
  🟡 Tier 2 — Medium Impact, Worth Planning

  5. "Find This Exact Item" from any image
  - User pastes any Instagram/Pinterest URL or uploads a screenshot
  - Bot finds the closest buyable item online
  - You have image search already — just expose it better with a dedicated flow
  - Market this as: "Seen it on Instagram? We'll find where to buy it"
  - This is genuinely unique and solves a real daily problem

  6. Budget Planner / Outfit Builder
  - "Build me a complete ethnic look under ₹3,000"
  - Bot assembles: kurta + dupatta + footwear + jewellery — one message, all pieces shown
  - Total cost shown: "Estimated: ₹2,840"
  - This is high perceived value — feels like a personal stylist

  7. Occasion-Based Recommendations
  - "I have a wedding on March 20" → bot remembers the date, reminds 1 week before with curated looks
  - Needs: very light calendar + notification system
  - High emotional value — solves real anxiety ("what do I wear to this wedding?")

  8. Size Guidance
  - User enters their measurements once
  - For each product: "Based on your measurements, order L on Myntra, M on Ajio (sizing varies)"
  - Reduces returns anxiety — huge purchase blocker in India
  - Needs: brand size chart data (can be scraped/curated manually for top 20 brands)

  ---
  🟠 Tier 3 — Nice to Have Later

  9. Social / Community
  - "Trending in your city" — show what's popular in Delhi vs Mumbai vs Bangalore
  - Share an outfit you built → get reactions
  - Builds organic growth (word of mouth)

  10. Personal Stylist Chat (Premium)
  - Free tier: AI chat
  - Paid tier: same AI but with a human stylist reviewing and commenting weekly
  - Human-in-the-loop = justifies ₹499+/mo easily

  ---
  What I'd Build First (Prioritized)

  Sprint 1 (Week 1-2): Style Profile Quiz + Persistent Wishlist
    → Makes every search feel personalized
    → Creates user lock-in
    → Needs: Clerk auth + Supabase (free tier — no cost)

  Sprint 2 (Week 3-4): "Find This on Instagram" flow
    → Unique feature, highly shareable
    → You already have image search — mostly UI work
    → Great for viral growth

  Sprint 3 (Week 5-6): Complete the Look (auto, one-click)
    → Increases time on app significantly
    → Drives more engagement per session

  Sprint 4 (Week 7-8): Price Alerts + Polish
    → First real reason to subscribe
    → Email via Resend.com
    → Then launch and charge

  ---
  The Subscription Angle




  🟢 Monetization Paths (realistic)

  Path 1 — Affiliate links (easiest, zero friction)
  - Flipkart, Amazon, Myntra all have affiliate programs
  - Replace product URLs with affiliate-tagged URLs
  - Earn 2–8% commission on purchases
  - Effort: 1–2 days | Revenue: passive, scales with traffic

  Path 2 — Freemium SaaS
  - Free: 10 chat queries/day
  - Paid ₹199–₹499/mo: unlimited searches, try-on feature, outfit completion
  - Use Razorpay (India) or Stripe for payments
  - Effort: 1–2 weeks | Revenue: predictable MRR

  Path 3 — B2B API / White-label
  - Sell the search API to small fashion brands/boutiques
  - They embed your chat widget on their site
  - Charge ₹2,000–₹10,000/mo per client
  - Effort: 2–4 weeks | Revenue: highest per customer

  Path 4 — Instagram/influencer tool
  - "Find this outfit" — user pastes Instagram image, bot finds where to buy it
  - This is your image search feature, marketed differently
  - Monetize via affiliate or ₹99/mo subscription
