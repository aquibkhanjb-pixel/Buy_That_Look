# AI Fashion Chatbot — Presentation Testing Guide

> **Purpose:** A step-by-step script to demo every major feature of the chatbot during
> a presentation. Each section lists what to type, what should happen, and what to highlight.

---

## Before You Start — Pre-flight Checklist

- [ ] Backend server running: `uvicorn app.main:app --reload` (port 8000)
- [ ] Frontend running: `npm run dev` (port 5173)
- [ ] Gemini API key set in `.env` and verified working
- [ ] FAISS index loaded (check terminal for "Loaded index with X vectors")
- [ ] Open browser at `http://localhost:5173`
- [ ] Open browser DevTools → Network tab (optional, to show API calls)
- [ ] Have a fashion image ready to upload (see section 5)

---

## Feature 1 — Basic Text Search (new_search intent)

**What to demonstrate:** Core search pipeline — Gemini features → CLIP → FAISS → Rerank → Response

**Type:**
```
Show me blue cotton kurtas for men
```

**What should happen:**
- Intent classified as `new_search`
- Features extracted: `{garment: "kurta", color: ["blue"], fabric: "cotton", gender: "men"}`
- 6–12 product cards appear
- Bot response is excited/helpful ("I found some great blue cotton kurtas for you!")
- Feature suggestion appended (e.g., "Try specifying: sleeve length or occasion")

**What to highlight:**
- "Notice the CLIP semantic search — it understands 'blue cotton kurta' visually, not just keyword matching"
- Point to the product cards: "These are ranked by Gemini's relevance score, not just visual similarity"
- Point to the suggestion chip: "The bot proactively suggests what else I can specify to narrow results"

---

## Feature 2 — Query Refinement (refine intent)

**Type (immediately after Feature 1):**
```
Show in white instead, under ₹1500
```

**What should happen:**
- Intent classified as `refine` (NOT new_search — conversation history is used)
- Features updated: color → ["white"], max_price → 1500
- New set of product cards, different from before
- Bot response acknowledges the change ("Sure! I've updated the colour to white and filtered to your budget")

**What to highlight:**
- "The intent changed from new_search to refine — it knows I'm modifying, not starting fresh"
- "The price filter is passed directly to FAISS — only products under ₹1500 are retrieved"
- "Gender (men) is still remembered even though I didn't mention it again"

---

## Feature 3 — Category Switch with Memory Reset

**Type (continuing the same chat):**
```
Now show me a ring to match
```

**What should happen:**
- Intent: `new_search` (completely different item)
- **Category switch detected**: shirt/kurta attributes reset, gender kept
- Products shown are rings, NOT kurtas with ring-related filters
- Feature suggestion is ring-specific: "Try specifying: metal (gold/silver/rose gold) or gemstone type"

**What to highlight:**
- "This is a key feature — the bot detects I switched from kurta to ring"
- "Colour, pattern, and style from the kurta search are wiped"
- "But if I had set my gender or budget, those would still apply to the ring search"
- "The suggestion is garment-specific — rings get metal/gemstone suggestions, not sleeve type"

---

## Feature 4 — Feedback Handling

### 4A — Positive Feedback

**Type:**
```
These look great!
```

**What should happen:**
- Intent: `feedback_positive`
- handle_feedback: `just_positive`
- No new search triggered
- Bot responds warmly: "Glad you like them! Would you like to see variations in different colours?"

**What to highlight:** "The bot doesn't waste an API call re-searching when you're happy"

---

### 4B — Negative Feedback with Refinement

**Type:**
```
Not exactly what I was looking for, show something more formal
```

**What should happen:**
- Intent: `feedback_negative`
- handle_feedback: `wants_refinement`
- Features updated: style → "formal"
- New products shown
- Bot response is apologetic + solution-focused

**What to highlight:** "Negative feedback loops back through the feature extraction — 'formal' is added to the filter set"

---

### 4C — Very Unsatisfied → Web Search

**Type:**
```
These are completely wrong, nothing is matching what I want, useless
```

**What should happen:**
- Intent: `feedback_negative`
- handle_feedback: `very_unsatisfied`
- Web search triggered — direct shopping links appear
- No product cards (local DB skipped)
- Bot response: apologetic, tells you to check the links

**What to highlight:** "When the local database fails to satisfy, the system escalates to web links automatically"

---

## Feature 5 — Image Upload (Vision Search)

**Prepare:** Have a fashion image ready (any kurta/dress/shirt photo)

**Upload the image** using the image button in the chat, then type:
```
Find similar products
```

**What should happen:**
- Gemini Vision describes the image: "Blue ethnic kurta, half sleeves, embroidered neckline"
- CLIP query built from image description
- Visually similar products returned
- Bot mentions it analysed the image

**What to highlight:**
- "The system uses Gemini Vision — a multimodal model — to describe the uploaded clothing"
- "That description becomes the CLIP text query, bridging vision and semantic search"
- "This is the hybrid pipeline: image understanding → text query → FAISS similarity search"

---

## Feature 6 — Marketplace / Platform Routing

**Type:**
```
Find blue kurtas on Flipkart
```

**What should happen:**
- Intent: `marketplace_search` (detected before Gemini even runs — keyword pre-check)
- Runs through `extract_fashion_features` first (important — handles image context too)
- Web search triggered, local DB skipped
- **Flipkart link shown first**, followed by Amazon, Myntra, Ajio
- URL format: `flipkart.com/search?q=blue+kurta` (properly encoded)

**What to highlight:**
- "Platform detection happens before Gemini classification — faster and more reliable"
- "The query still goes through feature extraction, so if I had uploaded an image + asked for Flipkart, the image description would be used in the search query"
- "Flipkart is always the first result since the user specifically asked for it"

**Also test Ajio specifically:**
```
Search for maroon sarees on Ajio
```
- Should show `ajio.com/search/?text=maroon+sarees` as the first link (previously this was broken)

---

## Feature 7 — Clarification Flow

**Start a fresh conversation (click New Chat)**

**Type (deliberately vague):**
```
Show me something nice
```

**What should happen:**
- Intent: `new_search`
- FAISS returns some results but Gemini scores them low (best score 3–5, quality = "mediocre")
- Bot asks ONE clarifying question: "What's the occasion — are you looking for something casual or formal?"
- No product cards yet

**Type an answer:**
```
Formal, for office
```

**What should happen:**
- Features updated: occasion → "office", style → "formal"
- Good results found this time (score ≥ 6)
- Clarification count reset to 0
- Products shown

**What to highlight:**
- "The system doesn't dump irrelevant results on you — it asks before showing poor matches"
- "After 2 rounds of clarification without improvement, it automatically escalates to web search"

---

## Feature 8 — General Conversation (non-search)

**Type:**
```
What can you help me with?
```

**What should happen:**
- Intent: `general`
- Skips all search nodes entirely
- Bot explains its capabilities conversationally
- No product cards

**Type:**
```
Hi, how are you?
```

**What should happen:**
- Intent: `general`
- Friendly conversational response
- No search triggered

**What to highlight:** "The bot recognises non-shopping messages and doesn't waste resources running a search"

---

## Feature 9 — Circuit Breaker / API Resilience

> **Note:** This is best explained conceptually unless you can simulate quota exhaustion.

**Explain what happens when Gemini API is unavailable:**

1. **Intent classification fails** → keyword-based fallback activates instantly (no delay)
2. **Feature extraction fails** → empty FashionFeatures, raw user message used as CLIP query
3. **Re-ranking fails** → all scores are null → system treats this as "good" quality (shows CLIP results, doesn't route to web search)
4. **Response generation fails** → pre-written message: *"My AI service is temporarily unavailable, but I found some visually similar products using image search"*
5. **60-second circuit breaker** → no further Gemini calls until cooldown expires

**What to highlight:**
- "The system never crashes or returns random products when the API fails"
- "CLIP alone is good enough for basic recommendations — Gemini is an enhancement, not a dependency"

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
*(Notice: gender=women, price, and formal style all persist — only colour updated)*

```
For beach instead
```
*(Occasion changes, but gender/price still remembered)*

**What to highlight:**
- "The `FashionFeatures` object accumulates across the entire conversation"
- "When I say 'in black', it knows to keep women/formal/₹2000 — it's a refinement, not a new search"
- "This state is maintained on the server AND mirrored to the frontend as a safety net"

---

## Quick Demo Script (5-minute version)

Use this condensed sequence for a time-limited demo:

| Step | Input | Feature Shown |
|------|-------|--------------|
| 1 | `Show me blue cotton kurtas for men` | Basic search, CLIP+FAISS, re-ranking |
| 2 | `In red, under ₹1000` | Refinement, session memory |
| 3 | `Now show me matching rings` | Category switch detection |
| 4 | `Find these on Myntra` | Marketplace routing, direct links |
| 5 | Upload image + `Find similar` | Gemini Vision, hybrid search |
| 6 | `Love these!` | Positive feedback handling |
| 7 | `What can you help me with?` | General intent, no wasted search |

---

## Things That Were Fixed (Good to Mention)

These are real bugs that were identified and fixed — shows production-level thinking:

| Bug | Fix |
|----|-----|
| Flipkart appearing as "brand" filter | Marketplace blocklist in feature extraction prompt |
| CLIP query included "a man wearing..." | LLM prompt rules — describe item only, not person |
| Category switch (shirt→ring) showing shirt colours | Category-switch detection, reset product-specific attrs |
| Ajio links returning 0 results | Fixed URL: `/search/?text=` instead of `/s/` |
| Web results empty even when search succeeded | `update_memory` no longer resets output fields |
| API quota exhaustion → random 12 products shown | Quality gate: null scores → "good" (show CLIP results) |
| 503 errors not caught by circuit breaker | Added "503"/"UNAVAILABLE" check with 30s backoff |
| Image ignored when platform mentioned | Marketplace now routes through feature extraction first |

---

## Common Interview Questions & Answers

**"How does the recommendation get better over time in a session?"**
> Each turn, `FashionFeatures` accumulates. Gender, budget, and style preferences persist. Only when you switch garment types do product-specific attributes reset. By turn 3–4, the CLIP query is highly specific, leading to much better FAISS results.

**"What's the latency?"**
> One turn takes roughly: 200ms (CLIP encode) + 300ms (FAISS search) + 800ms (Gemini classify + extract + rerank + response) = ~1.3 seconds total. The biggest variable is Gemini API response time.

**"What if the product database doesn't have what the user wants?"**
> The quality gate handles this: mediocre results → ask clarification, poor/empty results → web search with direct links. The user is never shown irrelevant results silently.

**"How does the image search work technically?"**
> Gemini Vision generates a text description of the image. That description is then encoded by CLIP into a 512-dimensional embedding. FAISS finds the nearest product embeddings in the index. This bridges the image-to-image gap using language as an intermediary.

**"Why not just use GPT-4 for everything?"**
> Cost and latency. Gemini Flash Lite is fast and cheap for classification/extraction tasks. CLIP + FAISS handles visual similarity at millisecond speed with no API cost after initial setup. We use Gemini Vision only for image uploads (one call), not for every search.
























 How to Verify Each Feature                                                                                                                                                                                                                                                                  
  Setup: Two windows open while testing

  1. Backend terminal — watch log output in real time
  2. Browser/Postman — send chat messages and inspect raw API response (JSON)

  ---
  Feature 1 — Negative Preference Memory

  Goal: After you say you dislike something, it should never appear again.

  Test script:
  Turn 1: "Show me men's kurtas"
  Turn 2: (look at results)
  Turn 3: "I don't like floral prints, show something else"
  Turn 4: "Show me more kurtas"
  Turn 5: "Show me something different, not red color"
  Turn 6: "More kurtas please"

  What to look for in logs:
  Negative preferences updated: {'patterns': ['floral']}
  Negative filter: 12 → 9 products          ← filtering happened

  Negative preferences updated: {'patterns': ['floral'], 'colors': ['red']}
  Negative filter: 12 → 7 products          ← cumulative filtering

  How to verify it's not hallucinating:
  - Turn 4 products should have NO floral in their titles/descriptions
  - Turn 6 products should have NO floral AND NO red
  - Check product titles manually in the response JSON

  Bug signal: Negative filter: 12 → 12 (nothing filtered — disliked feature not matching product text) or "Negative preferences updated" never 
  appears.

  ---
  Feature 2 — Slot Filling

  Goal: When critical info is missing, the bot asks the MOST IMPORTANT slot first, not a random question.

  Test script — Priority order test:
  Turn 1: "Show me something nice"
    → Expected question: "What type of clothing are you looking for? (kurta/dress/jeans…)"
    → Log: "top_slot=garment_type"

  Turn 2: "A kurta"
    → Expected question: "Is this for men or women?"
    → Log: "top_slot=gender"

  Turn 3: "For women"
    → Expected question: "What's the occasion?"
    → Log: "top_slot=occasion"

  What to look for in logs:
  Features extracted | missing_slots=['garment_type', 'gender', 'occasion', 'budget', 'color']
  Slot clarification #1 | top_slot=garment_type

  Hallucination check:
  - If Turn 1 asks "Do you have a color preference?" instead of garment_type → slot priority is broken
  - If the log shows top_slot=None when clearly slots are missing → _compute_missing_slots isn't running

  Shortcut to verify slots: After any search, look for this log line:
  Features extracted | missing_slots=['occasion', 'budget']
  The remaining missing slots should make sense given what the user has already told the bot.

  ---
  Feature 3 — Personalized Re-ranking

  Goal: The re-ranking prompt must include accumulated preferences, not just the current message.

  Test script:
  Turn 1: "I'm a woman looking for casual cotton kurtas under ₹1500"
    → Search happens, results shown

  Turn 2: "Show me more options"
    → Very vague — re-ranker must use session prefs to score correctly

  What to look for in logs:

  After Turn 2, the re-ranking internally builds a rich query. You won't see it in logs directly, but you can add a temporary log or check     
  LangSmith traces. In LangSmith:
  - Open the rerank_results span
  - Look at the input to llm_service.rerank_results()
  - The query argument should look like:
  Show me more options | User preferences: women kurta cotton casual for ₹1500
  - NOT just:
  Show me more options

  Hallucination check:
  - Turn 2 should NOT return men's products or formal wear, even though "show me more options" has no gender/style info
  - If Turn 2 results are random/uncorrelated to Turn 1 preferences → Feature 3 not working

  ---
  Feature 4 — Outfit Completion

  Goal: When you ask "what goes with this?", it must search for COMPLEMENTARY items, not more of the same.

  Test script:
  Turn 1: "Show me men's blue cotton kurta"
    → Results shown (kurtas)

  Turn 2: "What can I pair this with?"
    → Must NOT show more kurtas
    → Should show: churidar / palazzo / ethnic juttis / dupatta

  Turn 3: "What shoes go with this kurta?"
    → Should show: ethnic footwear / juttis / mojaris

  What to look for in logs:
  Intent classified: outfit_completion
  Outfit completion | ref='kurta' | query='men ethnic juttis to pair with kurta...'
  Parallel search | primary=12 secondary=8 unique=16

  Hallucination checks:
  - If log shows Intent classified: new_search instead of outfit_completion → keyword detection failed
  - If results are more kurtas → outfit_completion_node isn't overriding the search params
  - If ref='' → the node couldn't find the reference garment (check if last_shown is being persisted)

  Edge case test:
  Turn 1: (fresh session) "What goes with a saree?"
    → Should work even without previous search — uses 'saree' from the message

  ---
  Feature 5 — Parallel Search

  Goal: Two FAISS searches run simultaneously; the unique count should be MORE than just the primary alone.

  Test script:
  Any search where your raw query differs from the extracted CLIP query:
  "Find me something to wear to a beach wedding"
  The primary query will be structured features like "women dress beach casual" and the secondary will use the raw message "Find me something  
  to wear to a beach wedding".

  What to look for in logs:
  Parallel search | primary=12 secondary=8 unique=17
  - secondary should be > 0 (secondary search ran)
  - unique should be between max(primary, secondary) and primary + secondary

  Possible issue — secondary always = 0:
  This happens when raw_query == params.query (Gemini features produced an identical query to the raw message). This is rare for natural       
  language queries but common for already-structured inputs like "blue kurta men".

  How to force secondary search: Use a vague query:
  "Something nice for a party"
  Primary = "women party dress formal", Secondary = "Something nice for a party" → guaranteed to differ.

  ---
  Feature 6 — Result Explanation ("Why This?")

  Goal: Every product in the response JSON should have a match_reason field with a non-empty explanation.

  Test script:
  "Show me blue cotton kurta for men under ₹1200"

  How to inspect: Use browser DevTools → Network tab → find the /api/v1/chat/ POST → look at Response JSON:
  {
    "products": [
      {
        "title": "Men's Blue Cotton Kurta",
        "price": 999,
        "match_reason": "Matches: kurta, blue, within budget",
        ...
      },
      {
        "title": "Ethnic Cotton Shirt",
        "price": 850,
        "match_reason": "Matches: cotton fabric, within budget",
        ...
      }
    ]
  }

  Hallucination check:
  - If a product with title "Red Silk Dress" has match_reason: "Matches: kurta, blue" → the reason is lying (false match detection). This      
  shouldn't happen since the rule-based function checks string containment.
  - If match_reason: "" for ALL products → preferences weren't extracted correctly (check user_preferences is populated)
  - For strong matches (score ≥ 8), even empty-reason products get "Strong match" as fallback

  ---
  Quick Feature Health Check — One Session

  Run this single conversation to hit all 6 features at once:

  ┌──────┬──────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────┐   
  │ Turn │               Message                │                                      Feature Tested                                      │   
  ├──────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤   
  │ 1    │ "Show me something nice"             │ Feature 2 (asks garment_type slot)                                                       │   
  ├──────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤   
  │ 2    │ "A women's kurta"                    │ Feature 2 (asks next slot: occasion)                                                     │   
  ├──────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤   
  │ 3    │ "For a casual day out under ₹1000"   │ Feature 2 complete + Feature 5 (parallel search) + Feature 6 (check match_reason in      │   
  │      │                                      │ JSON)                                                                                    │   
  ├──────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤   
  │ 4    │ "I don't like floral or printed      │ Feature 1 (negative extraction + log)                                                    │   
  │      │ ones"                                │                                                                                          │   
  ├──────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤   
  │ 5    │ "Show more"                          │ Feature 1 (filter applied) + Feature 3 (prefs in rerank)                                 │   
  ├──────┼──────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤   
  │ 6    │ "What can I pair this with?"         │ Feature 4 (outfit completion)                                                            │   
  └──────┴──────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────┘   

  Check these in order after Turn 6:
  1. ✅ Log: Negative preferences updated after Turn 4
  2. ✅ Log: Negative filter: N → M after Turn 5
  3. ✅ Log: Intent classified: outfit_completion after Turn 6
  4. ✅ API response: match_reason field exists on Turn 3+ products
  5. ✅ Log: Parallel search | primary=X secondary=Y unique=Z on every search turn
  6. ✅ Log: Slot clarification #1 | top_slot=garment_type after Turn 1