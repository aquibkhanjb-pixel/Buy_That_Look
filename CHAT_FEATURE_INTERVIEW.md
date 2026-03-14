# AI Fashion Assistant — Interview Explanation Guide

## One-Line Summary
> "I built a multi-modal conversational fashion assistant using LangGraph and Gemini AI that understands natural language, extracts structured outfit attributes, searches the live web and Google Lens for real products, and completes outfits using a ReAct reasoning loop."

---

## How to Explain It Simply

### The Problem
"Regular search engines are keyword-based — you type 'blue kurta' and it shows blue kurtas. But real users say things like 'I need something for my cousin's wedding, not too expensive, my style is more boho.' A keyword search can't understand that. My chatbot can."

### The Solution
"I built a conversational AI that:
1. **Understands intent** — knows when you want to search vs. when you're just saying 'thanks'
2. **Extracts structured attributes** — pulls out colour, garment type, occasion, budget, style from natural conversation
3. **Remembers preferences** — if you said 'I'm looking for women's wear' in turn 1, you don't need to say it again in turn 5
4. **Searches the live web** — finds real products from Myntra, Ajio, Amazon, Flipkart using Serper.dev
5. **Uses Google Lens** — when you upload a photo, it finds visually identical products from across the internet"

---

## The Architecture — What to Draw on a Whiteboard

```
User message (+ optional image)
    ↓
Classify Intent (Gemini) — or keyword fallback if quota hit
    ↓
Extract Fashion Features (Gemini) ← KEY NODE
    ↓
Build structured web search query
    ↓
web_search node (3 parallel threads):
  ├── Serper text search (verified by Gemini Vision)
  ├── Visual web search     [if image uploaded]
  └── Google Lens           [if image uploaded]
    ↓
Merged + deduplicated results
    ↓
generate_response (Gemini) + feature suggestion hint
    ↓
update_memory (10-turn rolling window)
```

---

## The Key Technical Innovation — Feature Extraction Node

This is what makes the chatbot smarter than a basic search:

### What it does
Instead of passing the raw user message directly to the search engine,
we first call Gemini to extract **structured attributes**:

**User says:** "I want something flowy for Goa trip, not too expensive, like a boho vibe"

**Feature Extractor produces:**
```json
{
  "garment_type": "dress",
  "style": "boho",
  "occasion": "beach",
  "fit": "relaxed",
  "max_price": 1500,
  "gender": "women"
}
```

**Structured query built from features:** `"women boho beach dress relaxed under ₹1500"`

**This is much better than** passing "something flowy for Goa trip boho vibe" directly to a search engine, because structured queries produce far more precise results.

### Why it matters for interviews
- Shows you understand the gap between **natural language** and **search engine input**
- Demonstrates knowledge of **structured output with LLMs** (not just free-text generation)
- Explains why you need **two LLM calls** (classify intent + extract features) rather than one

---

## Memory — How It Works Across Turns

```
Turn 1: "Show me women's kurtas under ₹2000"
  → FashionFeatures: { garment="kurta", gender="women", max_price=2000 }

Turn 2: "In blue"
  → FashionFeatures.merge(): { garment="kurta", gender="women", max_price=2000, color=["blue"] }
  ← gender and price automatically carried forward

Turn 3: "Show me a ring to match"
  → Category switch detected! garment changed kurta → ring
  → Reset: color, style, fabric, fit (product-specific)
  → Keep: gender="women", max_price=2000 (user-level prefs)
```

`FashionFeatures.merge()` never overwrites existing values with None — this is the key invariant that makes multi-turn refinement work.

---

## Google Lens Integration

When the user uploads an image:

1. **Gemini Vision** describes the image → used for visual web search
2. **catbox.moe** hosts the image publicly (Serper Lens needs a URL, not base64)
3. **Serper `/lens`** returns visually identical products from across the internet
4. Results parsed from `"organic"` key, merged with text search results

This means a user can photograph an outfit anywhere in the world and find where to buy it online.

---

## Outfit Completion — ReAct Agent

"What goes with this?" triggers a 5-node ReAct subgraph:

```
Extract attributes from reference product
    ↓
Fashion stylist Gemini call → ideal complement + colour palette
    ↓
Generate search query
    ↓
Search Serper for complementary items
    ↓
Evaluate: do results match style + colour palette?
    ├── good → format_response
    └── poor + iter < 5 → refine query (loop)
```

This is **ReAct (Reason + Act)** — the model reasons about what it found, then decides whether to act again (refine) or stop.

---

## Resilience Mechanisms

| Failure | Response |
|---------|---------|
| Gemini quota (429) | 60s circuit breaker; keyword intent fallback |
| Gemini 503 | 30s circuit breaker; graceful error message |
| No products found | Direct shopping links: Myntra → Ajio → Amazon → Flipkart → Meesho |
| Image upload | catbox.moe + Serper Lens as backup to text search |

---

## One-Line Answer for "How does image search work?"

> "The user's image is uploaded to a free hosting service to get a public URL. That URL is sent to Serper's Google Lens endpoint, which returns visually similar products from across the internet. In parallel, Gemini Vision describes the image and that description is used for a separate text-based Serper search. Both results are merged and verified by Gemini Vision before showing to the user."

## One-Line Answer for "Why not use a local vector database?"

> "We removed FAISS and CLIP entirely. A local database gets stale, requires an embedding pipeline, and is limited to whatever we scraped. Serper.dev gives us real-time product discovery from every major Indian e-commerce site, and Google Lens finds visually identical products that no keyword query would surface. The quality and freshness is far superior."
