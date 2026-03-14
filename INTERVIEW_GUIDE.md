# Fashion Recommendation System — Interview Guide

## How to Introduce Your Project

### The Opening (30 seconds)

"I built an AI-powered fashion recommendation system with a conversational assistant at its core. Users can chat naturally — describe what they want, upload outfit photos, ask for outfit pairings — and the system searches live e-commerce sites, uses Google Lens for visual matching, and completes outfits using a reasoning agent. I also added a Trend Analyzer that pulls real fashion news and a virtual try-on feature using a diffusion model."

### The Problem Statement

"Traditional e-commerce search is keyword-based and context-free. If you say 'something boho for a Goa trip, not too expensive,' a keyword engine fails. And if you want to find an outfit you saw on Instagram, there's no way to search by photo across multiple Indian e-commerce sites. I wanted to build a system that understands fashion the way people naturally think about it — conversationally and visually."

### The Technical Overview

"The backend is built with FastAPI and orchestrated using LangGraph — a framework for building stateful AI pipelines as directed graphs. The AI nodes use Google Gemini for intent classification, structured feature extraction, and response generation. For product discovery, I use Serper.dev, which gives me real-time web search plus Google Lens for visual product matching. The frontend is Next.js with an editorial design system — Cormorant Garamond for the serif headers, a noir/ivory/gold palette."

---

## How to Structure Your Explanation Based on Time

### 2 minutes (elevator pitch):
Problem → LangGraph pipeline → Serper + Google Lens → one interesting challenge

### 5 minutes (standard):
Problem → Architecture overview → Feature extraction node → web_search parallel threads → Outfit ReAct → Trend Analyzer

### 10+ minutes (deep technical):
Walk through each LangGraph node → FashionFeatures merge semantics → Serper Lens integration → ReAct subgraph → resilience mechanisms → design decisions

---

## Common Interview Questions & How to Answer Them

### 1. "Walk me through the architecture."

**Your Answer:**

"The system is built around a LangGraph StateGraph — a directed graph of AI nodes with conditional routing. Every user message flows through this graph.

First, `classify_intent` uses Gemini to determine what the user wants: new search, refinement, outfit completion, feedback, or general conversation. There's a keyword fallback if Gemini is unavailable.

For search intents, `extract_fashion_features` calls Gemini to extract a structured `FashionFeatures` object — garment type, colour, style, occasion, budget, gender. This is far better than passing raw conversational text to a search engine.

Then `web_search` runs three parallel threads: a Serper text search, a visual web search using Gemini Vision's image description, and Google Lens for visually identical product matching. Results from all three merge and deduplicate by URL.

Finally, `generate_response` uses Gemini to write a conversational reply, and `update_memory` persists session state for up to 10 turns.

There's also a ReAct subgraph for outfit completion — a 5-node reasoning loop that searches for complementary items, evaluates style and colour compatibility, and refines the query if the results don't match."

---

### 2. "Why did you remove FAISS and CLIP?"

**Your Answer:**

"Originally the system used CLIP embeddings and a FAISS vector index for local product search. I removed them for three reasons.

First, freshness. A local database gets stale — products go out of stock, prices change, new collections arrive. Serper.dev gives real-time results from every major Indian e-commerce site without any scraping infrastructure.

Second, Google Lens. Serper's `/lens` endpoint finds visually identical products from across the internet — products that no keyword query would surface. CLIP could only search my local database.

Third, pipeline complexity. FAISS required an embedding pipeline — scrape products, generate CLIP embeddings, build the index, rebuild when products change. Removing it eliminated a huge maintenance burden with no quality loss — Serper's results are better than our scraped local database ever was.

The trade-off is that Serper is a paid API with per-request cost and latency, whereas FAISS search was free and fast. For this project, the quality improvement is worth it."

---

### 3. "How does the feature extraction work?"

**Your Answer:**

"Instead of passing the raw user message directly to the search engine, I call Gemini to extract a structured `FashionFeatures` object. For example, if the user says 'I want something flowy for a Goa trip, boho vibe, not too expensive,' Gemini extracts: garment_type='dress', style='boho', occasion='beach', max_price=1500, gender='women'. This structured representation builds a much more precise search query than the raw text.

What makes it powerful across turns is the `merge()` method. It accumulates attributes — if you said 'women's wear' in turn 1, that persists through all subsequent turns without the user repeating it. And it never overwrites existing values with None — that's the key invariant.

There's also category switch detection. If you go from searching kurtas to rings, product-specific attributes like colour, style, and fabric reset, but user-level preferences like gender and budget carry over."

---

### 4. "How does Google Lens work in your system?"

**Your Answer:**

"Serper's `/lens` endpoint requires a public HTTPS image URL — it doesn't accept base64. So when a user uploads an image, I first upload it to catbox.moe, a free image hosting service that requires no authentication, to get a public URL. Then I POST that URL to Serper's Lens endpoint.

The response comes back under the `'organic'` key — I discovered this during testing because the documentation mentioned `'visual_matches'` but the actual API uses `'organic'`. It can return up to 50 visually matching products from Google's image index.

These Lens results run in parallel with a text-based visual web search — Gemini Vision describes the image, and that description becomes a Serper text query. Both results merge. Products found via Lens get a blue 'Google Lens' badge in the UI; others get a green 'Web Search' badge."

---

### 5. "How does the outfit completion agent work?"

**Your Answer:**

"Outfit completion uses a ReAct — Reason and Act — pattern. When a user asks 'what goes with this?', a 5-node subgraph runs.

First, it extracts the reference product's attributes — colour, style, occasion — from the product that was last shown to the user. Then a 'fashion stylist' Gemini call determines the ideal complement: given a blue casual kurta, the stylist might recommend white/beige churidar pants or ethnic juttis.

Then it generates a search query, searches Serper for complementary items, and evaluates whether the results actually match the target style and colour palette. If they don't — say we got formal shoes instead of ethnic juttis — it refines the query and tries again. It loops up to 5 times. After 5 iterations it gives an apologetic response explaining the situation.

The key design decision is that outfit completion searches online only — it doesn't use any local database. And it routes directly to `update_memory` after finishing, bypassing the main `generate_response` node, because the subgraph handles its own response generation."

---

### 6. "How do you handle Gemini API failures?"

**Your Answer:**

"There are two layers of resilience.

The first is a circuit breaker in `_gemini_call()`. If Gemini returns a 429 quota error, I back off for 60 seconds — no further Gemini calls until the timer expires. For 503 service unavailable errors, the backoff is 30 seconds. This prevents hammering a down API.

The second layer is graceful degradation. For intent classification, a keyword-based fallback takes over — so 'not from Flipkart' correctly classifies as `feedback_negative` instead of defaulting to `new_search`. For feature extraction, the raw user message is used as the search query. For response generation, a pre-written message is shown: 'My AI service is temporarily unavailable, but here are the best matches.'

Critically, Serper still runs independently of Gemini. So even when Gemini is completely down, users still get product results — they just lose the AI-curated response text."

---

### 7. "What was the biggest technical challenge?"

**Your Answer:**

"The Google Lens integration had several layers of problems. First, the Serper plan I was on didn't include Lens — I got 403 errors. After upgrading, I hit a new problem: Serper Lens only accepts public HTTPS URLs, not base64. I solved this with catbox.moe for temporary image hosting.

Then the response had the wrong key — I was parsing `'visual_matches'` but the API returns `'organic'`. This took debugging to discover.

There was also a logic bug: the Lens search thread lived inside `search_local_db`, which had an early return for ethnic garments — so Lens never fired for sarees or lehengas. The fix was removing FAISS entirely and moving Lens into `web_search`, which always runs.

That bug actually motivated the broader FAISS removal — it forced me to think about the architecture holistically, and I realized the local database was more liability than asset."

---

### 8. "How would you scale this to production?"

**Your Answer:**

"A few areas need attention for production scale.

The session state currently lives in server memory, which doesn't survive restarts and doesn't work across multiple backend instances. I'd move it to Redis with a TTL, keyed by session ID.

Serper and Gemini are synchronous HTTP calls — I'd move to async clients with proper connection pooling to handle concurrent users without thread exhaustion.

The circuit breaker is currently in-process. In a multi-instance deployment, I'd need a distributed circuit breaker backed by Redis.

For cost, each chat turn makes 2–3 Gemini calls and 1–3 Serper calls. With Redis caching of repeat queries and Gemini response caching for common intents, I could reduce this significantly.

For the virtual try-on, HuggingFace free spaces are rate-limited. Production would need dedicated GPU compute or a managed diffusion API."

---

### 9. "How do you evaluate if the assistant is performing well?"

**Your Answer:**

"I look at it from two angles.

For the search quality, I check whether the Serper results are topically relevant — are we getting women's kurtas when asked for women's kurtas, not men's formal shirts. Gemini Vision's thumbnail verification step handles this automatically by batch-rejecting irrelevant products.

For the conversation quality, I track whether clarification fires correctly — vague queries should trigger one focused question, not dump poor results. And I track whether FashionFeatures accumulates sensibly across turns — gender and budget should persist, while switching from kurta to ring should reset style/colour.

For production, I'd add click-through tracking. If the user clicks a product link, that's a positive signal. If they immediately say 'these are completely wrong', that's a negative signal I can log. Over time, this data would let me tune which search queries and feature combinations lead to better outcomes."

---

### 10. "Can you explain LangGraph to a non-technical person?"

**Your Answer:**

"LangGraph is like a flowchart that your code actually runs. Imagine a customer service call centre. When a customer calls, the receptionist first figures out why they're calling — are they complaining, ordering something, or just asking a question? That's `classify_intent`.

Depending on the answer, they transfer to a different department. If it's a product order, they go to the orders team, who gathers all the details — what do you want, what colour, what size, what budget. That's `extract_fashion_features`.

The orders team then searches the warehouse — in our case, that's Serper.dev searching the live web. They check if the results look right, and then a response team writes back to the customer.

LangGraph lets me define each of these 'departments' as a node and the routing rules as edges — all in Python. It makes the AI pipeline auditable, testable, and easy to extend. If I want to add a new intent, I add a node and wire it in."

---

## Advanced Topics They Might Explore

### If the interviewer has ML/AI background:
- How does Gemini Vision verify search thumbnails?
- Why gemini-flash-lite and not a larger model?
- What's the trade-off between Serper text search and Google Lens?
- How do you handle hallucination in feature extraction?
- What's the FashionFeatures merge invariant and why does it matter?

### If the interviewer has systems/infrastructure background:
- How does the circuit breaker work across requests?
- Where is session state stored, and what are the failure modes?
- How would you handle the Serper rate limits at scale?
- What's the threading model inside web_search?
- How do you ensure the catbox.moe upload doesn't become a bottleneck?

### If the interviewer has product/business background:
- Why Serper over a direct Google Shopping API?
- What's the user journey through the Trend Analyzer → Chat pipeline?
- How would you monetize this?
- What's the biggest usability friction point?
- How would you A/B test different search strategies?

---

## Red Flags to Avoid

### Don't say:
- "I use CLIP for image search" — CLIP and FAISS are removed
- "I search my local database" — there is no local search anymore
- "The FAISS index has 1500 products" — outdated, no longer true
- "I use Gemini for re-ranking" — re-ranking removed with FAISS

### Do say:
- "All product search goes through Serper.dev — real-time, always fresh"
- "Google Lens finds visually identical products from across the internet"
- "LangGraph gives me explicit, auditable routing between AI nodes"
- "FashionFeatures.merge() accumulates preferences across the conversation without losing context"

---

## Final Confidence Booster

You built a system that:
1. Understands conversational fashion queries better than any keyword search
2. Finds products from live e-commerce sites — not a stale local database
3. Uses Google Lens to find products by image — something most e-commerce sites don't offer
4. Has a reasoning agent that builds complete outfits
5. Surfaces current trends from real fashion news
6. Lets users virtually try on clothes

That's a genuinely impressive portfolio project. Own it.
