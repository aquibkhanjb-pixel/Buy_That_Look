# Fashion Recommendation System — Technical Architecture

## Executive Summary

An AI-powered fashion recommendation system built around a conversational assistant. Users discover clothing and accessories through natural language chat, image uploads, or trend exploration. All product search is powered by live web search (Serper.dev) with Google Lens visual matching — no local product database required.

---

## Table of Contents
1. [System Overview](#1-system-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [AI Chat Pipeline — LangGraph](#3-ai-chat-pipeline--langgraph)
4. [Web Search & Google Lens](#4-web-search--google-lens)
5. [Trend Analyzer](#5-trend-analyzer)
6. [Virtual Try-On](#6-virtual-try-on)
7. [Technology Stack](#7-technology-stack)
8. [API Endpoints](#8-api-endpoints)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Key Design Decisions](#10-key-design-decisions)

---

## 1. System Overview

### Problem Statement
Fashion shoppers struggle to describe what they want. They might see an outfit on social media, have a vague style in mind, or want items that pair well together. Traditional keyword search fails them. They need a system that understands natural language, images, and context.

### Solution
A conversational AI stylist that:
- Understands fashion intent from natural language ("something boho for a beach trip under ₹1500")
- Finds visually similar products from a user's uploaded photo using Google Lens
- Stays current with fashion trends via live web intelligence
- Completes outfits using a ReAct reasoning loop
- Lets users virtually try on garments

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                         │
│  TrendAnalyzer │ ChatAssistant │ TryOnModal │ ProductModal    │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP / multipart/form-data
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                  Backend (FastAPI)                            │
│                                                              │
│  /api/v1/chat   ─── LangGraph StateGraph ──► Gemini AI       │
│  /api/v1/trends ─── Serper News + Gemini ──► 1hr cache       │
│  /api/v1/tryon  ─── gradio_client ─────────► HuggingFace     │
│  /api/v1/health ─── Liveness + readiness                     │
│                                                              │
│  External APIs:                                              │
│    Serper.dev  (text search + Google Lens + news)            │
│    Google Gemini (gemini-flash-lite-latest)                  │
│    catbox.moe  (image hosting for Lens)                      │
│    yisol/IDM-VTON (HuggingFace space for try-on)            │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
              PostgreSQL + Redis (cache)
```

---

## 3. AI Chat Pipeline — LangGraph

The chat assistant is a **directed StateGraph** (LangGraph) with conditional routing. Every user message flows through this graph.

### ChatState Fields
```python
class ChatState(TypedDict):
    messages: List[dict]          # conversation history (10-turn rolling window)
    intent: str                   # classified intent
    features: FashionFeatures     # extracted structured attributes
    web_results: List[dict]       # all results from web_search (merged)
    products_to_show: List[dict]  # product cards shown in UI
    image_bytes: bytes            # uploaded image
    image_b64: str                # base64 image for Gemini Vision
    image_description: str        # Gemini Vision description of image
    search_params: dict           # query string for web_search
    last_shown_product: dict      # reference product for outfit completion
    session: dict                 # persistent memory across turns
```

### Graph Flow

```
START
  │
  ▼
classify_intent  ← Gemini + keyword fallback
  │
  ├─ new_search / refine / marketplace_search ──► extract_fashion_features
  ├─ outfit_completion ────────────────────────► outfit_completion_node
  ├─ feedback_* ───────────────────────────────► handle_feedback_node
  └─ general ──────────────────────────────────► generate_response
                                                        │
                         ┌──────────────────────────────┘
                         ▼
              extract_fashion_features  ← Gemini extracts structured JSON
                         │
                         ├─ garment missing? ──► ask_clarification (max 2x)
                         └─ complete ──────────► web_search
                                                        │
                                                        ▼
                                                  web_search
                                            (3 parallel threads):
                                            1. Serper text search
                                            2. _run_visual_web() [if image]
                                            3. _run_lens()        [if image]
                                                        │
                                                        ▼
                                              generate_response  ← Gemini
                                                        │
                                                        ▼
                                               update_memory  ← trim to 10 turns
                                                        │
                                                       END
```

### Node Descriptions

| Node | Purpose |
|------|---------|
| `classify_intent` | Gemini classifies: new_search / refine / feedback_* / outfit_completion / general / marketplace_search. Keyword fallback if Gemini unavailable. |
| `extract_fashion_features` | Gemini extracts FashionFeatures (garment, color, style, occasion, budget, gender). Detects category switches — resets product-specific attrs, keeps gender+budget. |
| `web_search` | **Main search node.** Runs 3 threads in parallel: Serper text + visual web + Google Lens. Results merged and deduplicated by URL. |
| `generate_response` | Gemini generates conversational reply. Appends feature suggestion hint. Circuit breaker fallback message if Gemini unavailable. |
| `ask_clarification` | Slot-filling — ONE focused question. Fires max 2 times. |
| `handle_feedback_node` | Routes to: wants_refinement → re-extract; wants_different → re-extract; just_positive → generate_response; very_unsatisfied → web_search. |
| `outfit_completion_node` | Turn 1: asks clarifying question. Turn 2: invokes ReAct outfit subgraph. Routes directly to update_memory. |
| `update_memory` | Trims conversation history to 10 turns. Does NOT reset output fields (web_results, products_to_show). |

### FashionFeatures
```python
@dataclass
class FashionFeatures:
    garment_type: str       # "kurta", "dress", "ring", etc.
    gender: str             # "men", "women", "unisex"
    color: List[str]        # ["blue", "navy"]
    style: str              # "casual", "formal", "boho"
    occasion: str           # "wedding", "office", "beach"
    fabric: str             # "cotton", "silk"
    fit: str                # "slim", "relaxed"
    max_price: float        # budget ceiling
    brand: str              # specific brand
```
`FashionFeatures.merge()` never overwrites existing values with None — critical for cross-turn memory.

### ReAct Outfit Subgraph

When intent is `outfit_completion`, a separate 5-node subgraph runs:

1. `oa_extract_attributes` — Extract color/style/occasion from reference product
2. `oa_style_coordinate` — Fashion stylist Gemini call; sets ideal_style, color_palette, search_query, search_query_alt
3. `oa_generate_query` — Iter 0: stylist's query; Iter 1: alt query; Iter 2+: Gemini refines with hints
4. `oa_search_web` — Serper.dev for product cards; direct e-commerce links as fallback
5. `oa_evaluate_results` — Style-aware check vs ideal_style + color_palette
6. `oa_format_response` — Final response; apologetic if max 5 iterations reached

**Router:** good → format_response; poor/mismatch + iter<5 → generate_query (loop); iter≥5 → format_response

---

## 4. Web Search & Google Lens

### Serper Text Search
`_serper_react_search(query, context, num, max_iter=3)`:
- Fetches results from Serper.dev Shopping API
- Downloads product thumbnails in parallel (threads)
- Sends thumbnails to Gemini Vision for batch match/reject
- Refines query if fewer than 3 pass visual verification
- Falls back to raw results if Gemini Vision unavailable

### Google Lens Visual Search
`_serper_lens_search(image_bytes, num=6)`:
1. Upload image to catbox.moe (free, no auth) → public URL
2. POST to Serper `/lens` endpoint with `url` parameter
3. Parse `"organic"` key in response (not `"visual_matches"`)
4. Returns up to 50 visually matching product results

### Visual Web Search
`_run_visual_web(image_description, num=8)`:
- Uses Gemini Vision description as Serper text query
- Verifies thumbnails with Gemini Vision
- Results deduplicated with Lens results by URL

### Direct E-Commerce Links (Fallback)
When search returns no results: direct search URLs to:
1. Myntra → 2. Ajio → 3. Amazon → 4. Flipkart → 5. Meesho

---

## 5. Trend Analyzer

```
Serper /news ("fashion trends India 2026")
    ↓
Gemini extracts 6 TrendItem objects
    ↓
1-hour in-memory cache
    ↓
GET /api/v1/trends/
```

**TrendItem**: `name, description, category, badge, search_query, example_items`

**Fallback**: 6 static hardcoded trends when APIs fail.

Frontend renders horizontal scroll of trend cards. CTA button fires the `search_query` into ChatAssistant via a shared `triggerRef`.

---

## 6. Virtual Try-On

```
User uploads person photo
    ↓
POST /api/v1/tryon/
    ↓
gradio_client → yisol/IDM-VTON (HuggingFace)
    ↓  (~40 seconds, diffusion model)
result_image returned as base64
```

- Primary space: `yisol/IDM-VTON`
- Fallback: `Nymbo/Virtual-Try-On` (currently RUNTIME_ERROR)
- Garment image can be a `data:image/webp;base64,...` URL — decoded directly
- **Key**: `gradio_client 2.3.0` uses `token=` not `hf_token=`

---

## 7. Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS | Chat UI, trend cards, try-on modal |
| **UI Fonts** | Cormorant Garamond (serif) + DM Sans | Editorial fashion aesthetic |
| **Backend** | FastAPI, Python 3.10 | Async API, multipart form uploads |
| **AI Orchestration** | LangGraph (StateGraph) | Directed graph with conditional routing |
| **Language Model** | Google Gemini (gemini-flash-lite-latest) | Intent, features, ranking, response, vision |
| **Product Search** | Serper.dev (Shopping + Lens) | Real-time product discovery |
| **Image Hosting** | catbox.moe | Temporary public URL for Google Lens |
| **Try-On** | yisol/IDM-VTON (HuggingFace) | Diffusion-based virtual try-on |
| **Database** | PostgreSQL + SQLAlchemy | Product metadata (not used for search) |
| **Cache** | Redis | Response caching |
| **Conda env** | fashion-ai (Python 3.10) | Backend environment |

---

## 8. API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /api/v1/chat/` | POST | Main chat endpoint (multipart/form-data, supports image upload) |
| `GET /api/v1/trends/` | GET | Fetch 6 current fashion trends (1hr cached) |
| `GET /api/v1/trends/?refresh=true` | GET | Force-refresh trends cache |
| `POST /api/v1/tryon/` | POST | Virtual try-on with person + garment images |
| `GET /api/v1/products/` | GET | List products from DB with pagination |
| `GET /api/v1/products/{id}` | GET | Get single product details |
| `GET /api/v1/health` | GET | Basic health check |
| `GET /api/v1/health/ready` | GET | Readiness (DB + Redis) |
| `GET /api/v1/health/live` | GET | Liveness check |

---

## 9. Frontend Architecture

### Components
```
src/
├── app/
│   ├── page.tsx          # TrendAnalyzer + ChatAssistant (35 lines)
│   ├── layout.tsx        # Cormorant Garamond + DM Sans fonts
│   └── globals.css       # Tailwind base, scrollbar styling
├── components/
│   ├── Header.tsx        # Noir masthead with gold rule
│   ├── TrendAnalyzer.tsx # Horizontal trend cards with 1hr cache
│   ├── ChatAssistant.tsx # Full chat UI, product cards, web links
│   ├── TryOnModal.tsx    # Drag-drop, ~40s wait, before/after view
│   └── ProductModal.tsx  # Product detail overlay
├── lib/
│   └── api.ts            # API client (chat, trends, tryon)
└── types/
    └── index.ts          # TypeScript types
```

### Design System (Editorial Noir)
- `ivory` (#F5F0E8) — page background
- `noir` (#1A1A1A) — primary text, user message bubbles
- `gold` (#C9A84C) — accents, hover states, trend CTA
- `blush` (#F2D6D3) — women's category indicator

### Source Badges in Chat
- `google_lens` → blue "🔍 Google Lens"
- else → green "🛒 Web Search"

---

## 10. Key Design Decisions

### No Local Product Database for Search
FAISS + CLIP removed entirely. Serper.dev provides real-time product discovery with Google Lens for visual matching. This eliminates the cold-start problem, keeps results fresh, and removes the need for a scraping + embedding pipeline.

### LangGraph for Chat Orchestration
Explicit state machine makes routing auditable and debuggable. Conditional edges enforce business rules (e.g., max 2 clarifications) without if-else chains scattered through code.

### FashionFeatures Merge Semantics
`merge()` never overwrites existing values with None. Cross-turn memory is preserved without explicit persistence code in each node.

### Circuit Breaker for Gemini
60s cooldown for 429 (quota); 30s for 503 (temporary). When Gemini is down: keyword intent fallback + "AI temporarily unavailable" message. CLIP search removed — Serper still runs independently.

### Image Upload Architecture
Chat endpoint is `multipart/form-data` (not JSON). Image bytes passed through graph state. Google Lens and visual web search fire as parallel threads inside `web_search` only when image is present.

### Outfit Completion Isolation
ReAct subgraph searches online only (no local DB). `outfit_completion_node` routes directly to `update_memory`, bypassing `generate_response` (subgraph handles its own response generation).
