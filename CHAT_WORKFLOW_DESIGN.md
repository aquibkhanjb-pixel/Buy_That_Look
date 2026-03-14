# AI Fashion Assistant — Production Workflow Design

## Architecture Summary

| Decision | Choice |
|----------|--------|
| Product search | Serper.dev (live web search + Google Lens) |
| Local DB search | Removed (FAISS/CLIP deleted) |
| Memory | Session only (10-turn rolling window) |
| Image in chat | Yes — multipart/form-data upload |
| Max turns | 10 (older messages dropped) |
| Feature extraction | Gemini → structured FashionFeatures JSON |
| Image hosting for Lens | catbox.moe (free, no auth required) |
| Validation | Pydantic throughout — all state fields typed |

---

## Full Graph Flow

```
User Input (text / image / both)
         ↓
  [ classify_intent ]  ← Gemini reads message + 10-turn history
         │                keyword fallback if Gemini unavailable
         │
         ├─ new_search / refine / marketplace_search
         │         ↓
         │  [ extract_fashion_features ]  ← Gemini structured JSON
         │         │      FashionFeatures.merge() preserves cross-turn attrs
         │         │
         │         ├─ garment missing? ──► [ ask_clarification ] ─► END (max 2x)
         │         │
         │         └─ complete ──────────► [ web_search ]
         │                                      │
         │                              ┌───────┼────────┐
         │                              ▼       ▼        ▼
         │                         Serper   visual   Google
         │                          text     web      Lens
         │                         search   search   search
         │                        (always) (image)  (image)
         │                              │       │        │
         │                              └───────┴────────┘
         │                                      │
         │                                merge + dedup
         │                                      │
         │                                      ▼
         │                           [ generate_response ]  ← Gemini
         │                                      │
         │                                      ▼
         │                            [ update_memory ]  ← trim to 10 turns
         │                                      │
         │                                     END
         │
         ├─ outfit_completion
         │         ↓
         │  [ outfit_completion_node ]
         │    Turn 1: ask clarifying question ──────────────────► [ update_memory ] → END
         │    Turn 2: invoke ReAct subgraph ───────────────────► [ update_memory ] → END
         │
         ├─ feedback_positive / feedback_negative
         │         ↓
         │  [ handle_feedback_node ]
         │    wants_refinement / wants_different ──► [ extract_fashion_features ]
         │    just_positive ────────────────────────► [ generate_response ]
         │    very_unsatisfied ────────────────────────► [ web_search ]
         │
         └─ general
                   ↓
           [ generate_response ]  ← no search triggered
```

---

## Full Mermaid Diagram

```mermaid
flowchart TD
    START(["`**User Message**
    text | image | text+image`"]) --> classify_intent

    classify_intent{"`**classify_intent**
    Gemini + keyword fallback
    10-turn history`"}

    classify_intent -->|new_search / refine / marketplace| extract_features
    classify_intent -->|outfit_completion| outfit_node
    classify_intent -->|feedback| feedback_node
    classify_intent -->|general| generate_response

    extract_features["`**extract_fashion_features**
    Gemini → FashionFeatures JSON
    merge() preserves cross-turn memory
    category switch detection`"]

    extract_features -->|garment missing| ask_clarification
    extract_features -->|complete| web_search

    ask_clarification["`**ask_clarification**
    ONE focused question
    max 2x per conversation`"]
    ask_clarification --> update_memory

    web_search["`**web_search**
    3 parallel threads:
    ① Serper text search
    ② visual web search (image)
    ③ Google Lens (image)
    merge + dedup by URL`"]

    web_search --> generate_response

    generate_response["`**generate_response**
    Gemini conversational reply
    + feature suggestion hint
    circuit breaker fallback`"]
    generate_response --> update_memory

    update_memory["`**update_memory**
    trim to 10 turns
    persist session state
    last_shown_product`"]
    update_memory --> END([END])

    outfit_node["`**outfit_completion_node**
    Turn 1: clarify item type
    Turn 2: ReAct subgraph`"]
    outfit_node --> update_memory

    feedback_node{"`**handle_feedback**
    classify sub-intent`"}
    feedback_node -->|wants_refinement / different| extract_features
    feedback_node -->|just_positive| generate_response
    feedback_node -->|very_unsatisfied| web_search
```

---

## ReAct Outfit Subgraph

```mermaid
flowchart TD
    A([outfit_completion_node Turn 2]) --> B

    B["`**oa_extract_attributes**
    color / style / occasion
    from reference product`"]

    B --> C["`**oa_style_coordinate**
    Fashion stylist Gemini call
    → ideal_style, color_palette
    → search_query, search_query_alt`"]

    C --> D["`**oa_generate_query**
    Iter 0: stylist search_query
    Iter 1: search_query_alt
    Iter 2+: Gemini refines`"]

    D --> E["`**oa_search_web**
    Serper.dev product cards
    → direct links fallback`"]

    E --> F{"`**oa_evaluate_results**
    check category + style/colour
    vs ideal_style + color_palette`"}

    F -->|good| G["`**oa_format_response**
    generate final response`"]
    F -->|"poor + iter < 5"| D
    F -->|iter ≥ 5| G

    G --> END([update_memory → END])
```

---

## ChatState — All Fields

```python
class ChatState(TypedDict):
    # Conversation
    messages: List[dict]           # rolling 10-turn history
    session_id: str
    intent: str                    # classified intent
    session: dict                  # persistent: gender, budget, last_shown, disliked_features

    # Feature extraction
    features: FashionFeatures      # accumulated across turns
    image_bytes: Optional[bytes]   # uploaded image
    image_b64: Optional[str]       # base64 for Gemini Vision
    image_description: Optional[str]  # Gemini Vision output

    # Search
    search_params: dict            # query string for web_search
    web_results: List[dict]        # merged results from all 3 threads
    lens_results: List[dict]       # raw Google Lens results
    products_to_show: List[dict]   # product cards rendered in UI

    # Output
    response_text: str             # generated reply
    web_search_triggered: bool
    clarification_count: int

    # Outfit completion
    last_shown_product: dict       # reference product for ReAct
    outfit_state: OutfitState      # ReAct subgraph state
```

**Removed fields** (FAISS era — no longer exist):
- ~~`local_results`~~
- ~~`final_results`~~
- ~~`results_quality`~~

---

## Serper.dev Integration

### Text Search
```
query = "women boho beach dress under ₹1500 Myntra Ajio"
POST https://google.serper.dev/shopping
headers: { X-API-KEY: SERPER_API_KEY }
body: { q: query, gl: "in", num: 10 }
→ parse results → Gemini Vision thumbnail verification
```

### Google Lens
```
image_bytes → catbox.moe (POST fileupload) → public_url
POST https://google.serper.dev/lens
body: { url: public_url }
→ parse response["organic"] (NOT "visual_matches")
→ return product list
```

### News (for Trend Analyzer)
```
query = "fashion trends India 2026"
POST https://google.serper.dev/news
→ articles → Gemini extracts 6 TrendItem objects → 1hr cache
```

---

## Verified Platform Search URLs

| Platform | URL Pattern |
|----------|------------|
| Flipkart | `https://www.flipkart.com/search?q={quote_plus}` |
| Amazon | `https://www.amazon.in/s?k={quote_plus}` |
| Myntra | `https://www.myntra.com/search?rawQuery={quote_plus}` |
| Ajio | `https://www.ajio.com/search/?text={quote_plus}` |
| Meesho | `https://www.meesho.com/search?q={quote_plus}` |
| Nykaa | `https://www.nykaafashion.com/search?q={quote_plus}` |
| Snapdeal | `https://www.snapdeal.com/search?keyword={quote_plus}` |
