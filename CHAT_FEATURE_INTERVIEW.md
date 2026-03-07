# AI Fashion Assistant — Interview Explanation Guide

## One-Line Summary
> "I built a multi-modal conversational fashion assistant using LangGraph and Gemini AI that understands natural language, extracts structured outfit attributes, searches a vector database, and falls back to live web search when local results aren't good enough."

---

## How to Explain It Simply

### The Problem
"Regular search engines are keyword-based — you type 'blue kurta' and it shows blue kurtas. But real users say things like 'I need something for my cousin's wedding, not too expensive, my style is more boho.' A keyword search can't understand that. My chatbot can."

### The Solution
"I built a conversational AI that:
1. **Understands intent** — knows when you want to search vs. when you're just saying 'thanks'
2. **Extracts structured attributes** — pulls out colour, garment type, occasion, budget, style from natural conversation
3. **Remembers preferences** — if you said 'I'm looking for women's wear' in turn 1, you don't need to say it again in turn 5
4. **Falls back to web** — if our database doesn't have what you want, it searches Ajio, Myntra, Amazon for you"

---

## The Architecture — What to Draw on a Whiteboard

```
User message
    ↓
Classify Intent (Gemini)
    ↓
Extract Fashion Features (Gemini) ← KEY NODE
    ↓
Build CLIP Query from structured features
    ↓
FAISS Vector Search
    ↓
Gemini Re-ranking (score each result 0-10)
    ↓
Quality Gate: good? → show results
              poor? → ask clarification (max 2x)
              still poor? → web search fallback
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

**CLIP Query built from features:** `"women dress boho for beach relaxed"`

**This is much better than** passing "something flowy for Goa trip boho vibe" directly to CLIP,
because CLIP works best with specific fashion descriptors, not conversational language.

### Why it matters for interviews
- Shows you understand the gap between **natural language** and **embedding model input**
- Demonstrates knowledge of **structured output with LLMs** (not just free-text generation)
- Explains why you need **two LLM calls** (classify intent + extract features) rather than one

---

## Memory — How It Works Across Turns

```
Turn 1: "Show me kurtas for men"
         → user_preferences = {gender: "men", garment_type: "kurta"}

Turn 2: "Under 800 rupees"
         → current_features = {max_price: 800}
         → merged = {gender: "men", garment_type: "kurta", max_price: 800}  ✓ memory works!

Turn 3: "In blue"
         → current_features = {color: ["blue"]}
         → merged = {gender: "men", garment_type: "kurta", max_price: 800, color: ["blue"]}  ✓
```

**Key design decision:** Features are merged using a `merge()` method that
**never overwrites with None** — so saying "in blue" doesn't erase the gender or budget.

**How memory is implemented:**
- Server-side: `ChatService` stores accumulated preferences in a Python dict keyed by `conversation_id`
- Client-side: Frontend also mirrors preferences and sends them back on each request (safety net)
- Rolling window: last 10 conversation turns are kept; older ones are dropped to manage token limits

---

## The LangGraph Connection

### Why LangGraph and not just if/else?

| Approach | Problem |
|----------|---------|
| Simple if/else | Hard to maintain, no state management, can't add nodes easily |
| LangGraph StateGraph | Clean graph structure, typed state, built-in conditional routing, easy to extend |

### What LangGraph gives us
1. **StateGraph** — all nodes share typed state (`ChatState TypedDict`), no global variables
2. **Conditional edges** — routing logic (quality_router, intent_router, feedback_router) is clean and testable
3. **Composability** — easy to add new nodes (e.g. a "style advice" node) without touching other nodes

### The graph structure
```python
graph.add_conditional_edges(
    "classify_intent",
    lambda s: "extract_features" if s["intent"] in ("new_search", "refine")
              else "handle_feedback" if "feedback" in s["intent"]
              else "generate_response",
    {...}
)
```
This is the core routing logic — clean, readable, testable.

---

## The Web Search Fallback

### When does it trigger?
1. Local FAISS search returns empty results
2. Best Gemini re-ranking score < 3 (very poor match)
3. User says "I don't like any of these" (very_unsatisfied feedback)
4. User has been asked clarifying questions twice with no improvement

### How it works
1. Gemini generates 3-5 targeted search queries from the extracted features
2. Tries Gemini Grounding (google_search tool) for live results
3. Falls back to generating direct e-commerce search links (Ajio, Myntra, Amazon, Flipkart)

### Example
```
user_preferences = {garment_type: "kurta", color: ["blue"], gender: "men", max_price: 1000}
→ Generated queries: ["blue cotton kurta men", "mens ethnic blue kurta", "light blue kurta under 1000"]
→ Direct links: ajio.com/s/blue+cotton+kurta+men, myntra.com/blue+cotton+kurta+men ...
```

---

## Pydantic Validation — Why It Matters

"I used Pydantic for all data models in the chat system because:
1. **Type safety** — if Gemini returns a price as a string, Pydantic coerces it to float
2. **Validation** — search k must be between 1-50, enforced at the data layer
3. **Serialization** — clean `.model_dump()` to pass between LangGraph nodes
4. **The `merge()` method** — I added a custom method on `FashionFeatures` to accumulate preferences across turns safely"

---

## Multi-modal Input in Chat

"The chat tab supports both text and image input:
- User uploads an image → Gemini Vision describes it → description fed into Feature Extractor
- User adds text → combined with image description
- CLIP encodes both → hybrid embedding (65% visual + 35% text)

This means you can upload a dress photo and say 'find something similar but in blue' — the system understands both signals."

---

## Metrics / Results

- **Query expansion** lifts result quality: "beach party" → 16 results with 8.0 avg score vs. 3 results with 4.0
- **Feature extraction** improves precision: structured CLIP query outperforms raw conversational text
- **Re-ranking**: filters out irrelevant results — scores < 3 are hidden, scores 3-5 shown as "possible matches"
- **Web fallback**: ensures user always gets SOMETHING useful even when our database has no match

---

## Common Interview Questions

**Q: Why not just send the user's message directly to CLIP?**
A: "CLIP is trained on image-text pairs with short, descriptive captions — not conversational language. 'Something flowy for Goa trip boho vibe' gets much worse results than 'women boho beach relaxed dress'. The Feature Extraction node bridges the gap between how users talk and how CLIP understands."

**Q: Why two separate LLM calls (classify_intent + extract_features)?**
A: "Separation of concerns. Mixing routing logic with feature extraction in one prompt leads to worse results on both tasks. Intent classification needs to focus on the conversational context. Feature extraction needs to focus on fashion attributes. Two focused calls outperform one mixed call."

**Q: How do you handle the latency of multiple Gemini calls?**
A: "The full pipeline (classify intent + extract features + re-rank + generate response) takes about 4-6 seconds. I mitigate this with a typing indicator in the UI, and the quality improvement justifies the wait. For production at scale, I'd cache embeddings for repeated queries and potentially batch calls."

**Q: What would you add next?**
A: "A user profile that persists across sessions (PostgreSQL storage), outfit combination suggestions ('this kurta pairs well with...'), and a size recommendation based on brand-specific size charts."

---

## Tech Stack Summary

| Component | Technology |
|-----------|-----------|
| Conversation orchestration | LangGraph StateGraph |
| Intent + feature extraction | Google Gemini (gemini-flash-lite-latest) |
| Visual + text embeddings | OpenAI CLIP (ViT-B/32) |
| Vector search | FAISS |
| Web fallback | Gemini Grounding + direct e-commerce links |
| Data validation | Pydantic v2 |
| API | FastAPI |
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| Data store | PostgreSQL + 1,544 Ajio products |
