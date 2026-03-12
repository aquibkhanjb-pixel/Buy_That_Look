"""
AI Fashion Assistant — Production LangGraph Chat Service (v3)

Main graph architecture:

  START
    ↓
  classify_intent          ← Gemini: new_search / refine / feedback_* / outfit_completion / general
    ↓ (conditional)
    ├── [new_search|refine]     → extract_fashion_features
    │                                 ↓ (_post_extract_router)
    │                              ┌─ marketplace_search  → web_search
    │                              ├─ garment missing (1st turn) → ask_clarification
    │                              └─ otherwise           → search_local_db
    │                                                           ↓
    │                                                       rerank_results
    │                                                           ↓ (quality_router)
    │                                                        ┌─ good     → generate_response
    │                                                        ├─ mediocre → ask_clarification
    │                                                        └─ poor     → web_search
    │
    ├── [outfit_completion]     → outfit_completion_node
    │                                 ↓ (direct edge)
    │                              update_memory    ← ReAct subgraph runs INSIDE the node
    │
    ├── [feedback_*]            → handle_feedback
    │                                 ↓ (feedback_router)
    │                              ┌── wants_refinement → extract_fashion_features
    │                              ├── just_positive    → generate_response
    │                              └── wants_different / very_unsatisfied → web_search
    │
    └── [general]               → generate_response

  web_search → generate_response → update_memory → END
  ask_clarification → update_memory → END

ReAct Outfit Subgraph (runs inside outfit_completion_node):
  START → oa_extract_attributes → oa_generate_query → oa_search_web
       → oa_evaluate_results → [_outfit_react_router]
            ├── good or max_iter (5) → oa_format_response → END
            └── poor/mismatch        → oa_generate_query  (loop)
"""

import json
import re
import threading
import time
import urllib.parse
from typing import List, Optional, TypedDict, Dict, Any

from loguru import logger

try:
    from langsmith import traceable
except ImportError:
    def traceable(**_kwargs):  # type: ignore[misc]
        def decorator(fn):
            return fn
        return decorator

try:
    from langgraph.graph import StateGraph, START, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.warning("langgraph not installed — chat will use simple fallback")

from app.schemas.chat import FashionFeatures, SearchParams, WebSearchResult
from app.services.llm_service import llm_service
from app.services.search_engine import search_engine


# ─────────────────────────────────────────────────────────────────────────────
# LangGraph State
# ─────────────────────────────────────────────────────────────────────────────

class ChatState(TypedDict):
    # Conversation history (full, trimmed to 10 turns in update_memory)
    messages: List[dict]
    conversation_id: str

    # Per-turn input
    input_type: str               # "text" | "image" | "hybrid"
    raw_query: str
    image_description: Optional[str]   # Gemini Vision output (if image provided)

    # Feature extraction (this turn + accumulated session)
    current_features: dict        # FashionFeatures serialized dict (this turn)
    user_preferences: dict        # Accumulated FashionFeatures across session

    # Search
    search_params: dict           # SearchParams serialized dict
    local_results: List[dict]
    final_results: List[dict]
    results_quality: str          # "good" | "mediocre" | "poor" | "empty"

    # Web search fallback
    web_search_triggered: bool
    search_queries: List[str]
    web_results: List[dict]       # List[WebSearchResult dicts]

    # Intent / routing
    intent: str                   # "new_search"|"refine"|"feedback_positive"|"feedback_negative"|"general"|"marketplace_search"
    feedback_action: str          # "text_response"|"wants_refinement"|"wants_different"|"very_unsatisfied"
    target_marketplace: str       # e.g. "flipkart" — set when user asks for a specific platform

    # Clarification tracking (persisted across turns)
    clarification_count: int

    # Response
    response: str
    products_to_show: List[dict]

    # ── New robustness fields ──────────────────────────────────────────────
    # Feature 1 — Negative Preference Memory
    disliked_features: dict        # {"colors":[], "patterns":[], "styles":[], "brands":[], "garment_types":[]}

    # Feature 2 — Slot Filling
    missing_slots: List[str]       # Prioritised list: ["garment_type","gender","occasion","budget","color"]

    # Feature 4 — Outfit Completion
    outfit_context: str            # Title/description of the reference item the user wants to complement
    last_shown_product: dict       # Full product dict of the FIRST result shown last turn (for ReAct outfit matching)

    # Cross-turn search context (prevents wrong-category web searches after outfit completion)
    last_search_query: str         # The actual CLIP/search query used in the previous turn

    # Outfit completion — waiting for user to specify what TYPE of item they want
    awaiting_outfit_detail: bool   # True when bot asked "footwear/accessories/bottom?" and waiting for answer


# ─────────────────────────────────────────────────────────────────────────────
# OutfitState — isolated state for the ReAct outfit completion subgraph
# ─────────────────────────────────────────────────────────────────────────────

class OutfitState(TypedDict):
    # Input context
    reference_product: dict        # Full product dict shown to user (title, price, image, etc.)
    reference_attributes: dict     # Extracted: color, style, garment_type, occasion, pattern
    complement_type: str           # "footwear" | "accessories" | "bottom" | "top"
    user_gender: str               # Preserved from parent FashionFeatures
    user_budget: Optional[float]   # Max price from parent state

    # Specific item requested (e.g. "watch", "heels") — more precise than complement_type ("accessories")
    complement_item: str           # Exact keyword from user message; used in queries over complement_type

    # ReAct loop control
    iteration: int                 # Current iteration count (starts at 0, max 5)
    current_query: str             # Search query for this iteration
    refinement_hints: List[str]    # What failed in previous iterations (for smarter retries)

    # Per-iteration results
    web_results: List[dict]        # Results from this iteration's web search
    evaluation: str                # "good" | "poor" | "mismatch"
    evaluation_reason: str         # Why it's good/poor

    # Final output (set by oa_format_response)
    outfit_response: str           # Text response to show in chat
    outfit_web_results: List[dict] # Web result links to display


# ─────────────────────────────────────────────────────────────────────────────
# Helper Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _get_last_user_message(messages: List[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""

def _format_history(messages: List[dict], max_turns: int = 6) -> str:
    recent = messages[-max_turns * 2:] if len(messages) > max_turns * 2 else messages
    lines = []
    for m in recent:
        role = "User" if m.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {m.get('content', '')}")
    return "\n".join(lines)

def _clean_json(text: str) -> str:
    """Strip markdown code fences from LLM JSON output."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


# Circuit breaker: skip Gemini calls for 60 s after a 429 error
_rate_limited_until: float = 0.0


@traceable(name="gemini_call", run_type="llm", tags=["gemini", "chat"])
def _gemini_call(prompt: str) -> Optional[str]:
    """Make a Gemini API call. Returns text or None on failure.

    Implements a 60-second circuit breaker when the API returns 429 so that
    subsequent nodes in the same request don't waste time on doomed calls.
    """
    global _rate_limited_until
    if not llm_service.is_enabled:
        return None
    if time.time() < _rate_limited_until:
        logger.debug("Gemini rate-limit circuit breaker active — skipping call")
        return None
    try:
        response = llm_service._client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as exc:
        exc_str = str(exc)
        if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
            _rate_limited_until = time.time() + 60
            logger.warning("Gemini quota exceeded — circuit breaker active for 60 s")
        elif "503" in exc_str or "UNAVAILABLE" in exc_str:
            _rate_limited_until = time.time() + 30
            logger.warning("Gemini service unavailable — circuit breaker active for 30 s")
        else:
            logger.warning(f"Gemini call failed: {exc}")
        return None


# ReAct outfit subgraph singleton (compiled in ChatService.initialize)
_outfit_agent: Any = None


# Known e-commerce marketplaces (for platform-aware routing)
_MARKETPLACES = {
    "flipkart", "amazon", "myntra", "ajio", "meesho",
    "nykaa", "snapdeal", "tata cliq", "tatacliq", "shopsy",
}


def _detect_marketplace(msg: str) -> Optional[str]:
    """Return the marketplace name if the user is asking for a specific platform."""
    m = msg.lower()
    platform_triggers = ("from", "on", "via", "through", "buy on", "search on", "show on", "find on")
    for marketplace in _MARKETPLACES:
        if marketplace in m and any(t in m for t in platform_triggers):
            return marketplace
    return None


def _keyword_intent(msg: str) -> str:
    """
    Simple keyword-based intent classifier used as fallback when Gemini is unavailable.
    Prevents misclassifying feedback as new_search when the API is down.
    """
    m = msg.lower()
    negative = {"not what", "don't like", "doesn't", "wrong", "bad", "hate", "dislike",
                "aren't", "are not", "not from", "not showing", "nothing", "useless",
                "these are wrong", "these are not", "show something else"}
    positive = {"love it", "great", "nice", "perfect", "amazing", "looks good",
                "i like", "good choice", "that's nice", "thanks"}
    refine = {"under", "below", "above", "cheaper", "more expensive",
              "in red", "in blue", "different color", "different style",
              "another", "instead", "budget", "price range"}
    search = {"show me", "find me", "recommend", "looking for", "i want",
              "search for", "get me", "suggest", "need a", "find a"}
    outfit = {"goes with", "match with", "pair with", "wear with", "complete outfit",
              "outfit with", "style with", "what to wear", "complement", "complete the look",
              "goes well with"}

    if any(kw in m for kw in outfit):
        return "outfit_completion"
    if any(kw in m for kw in negative):
        return "feedback_negative"
    if any(kw in m for kw in positive):
        return "feedback_positive"
    if any(kw in m for kw in refine):
        return "refine"
    if any(kw in m for kw in search):
        return "new_search"
    # Short messages with no clear search signal → treat as general (conversational)
    if len(m.split()) <= 5:
        return "general"
    return "new_search"


# ─────────────────────────────────────────────────────────────────────────────
# Feature 2 — Slot Filling Helper
# ─────────────────────────────────────────────────────────────────────────────

def _compute_missing_slots(features: FashionFeatures) -> List[str]:
    """Return prioritised list of critical attributes still unspecified."""
    missing: List[str] = []
    if not features.garment_type: missing.append("garment_type")
    if not features.gender:       missing.append("gender")
    if not features.occasion:     missing.append("occasion")
    if not features.max_price:    missing.append("budget")
    if not features.color:        missing.append("color")
    return missing


# ─────────────────────────────────────────────────────────────────────────────
# Feature 1 — Negative Preference Extraction Helper
# ─────────────────────────────────────────────────────────────────────────────

def _extract_negative_features(msg: str, current_dislikes: dict) -> dict:
    """
    Use Gemini to extract fashion attributes the user dislikes from their message.
    Merges newly found dislikes with the accumulated dislike history.
    """
    if not llm_service.is_enabled:
        return current_dislikes

    prompt = (
        "Extract fashion attributes the user DISLIKES from this message.\n"
        f"Message: '{msg}'\n\n"
        "Return a JSON object (no markdown) with these keys (empty list [] if nothing mentioned):\n"
        "{\n"
        '  "colors": [],\n'
        '  "patterns": [],\n'
        '  "styles": [],\n'
        '  "brands": [],\n'
        '  "garment_types": []\n'
        "}\n"
        "Examples:\n"
        "  'I don\\'t like floral'  → {\"patterns\": [\"floral\"]}\n"
        "  'Not a fan of red'      → {\"colors\": [\"red\"]}\n"
        "  'Too formal for me'     → {\"styles\": [\"formal\"]}\n"
        "Return ONLY the JSON."
    )

    raw = _gemini_call(prompt)
    if not raw:
        return current_dislikes

    try:
        parsed = json.loads(_clean_json(raw))
        result = {
            "colors":        list(set((current_dislikes.get("colors") or [])        + (parsed.get("colors") or []))),
            "patterns":      list(set((current_dislikes.get("patterns") or [])      + (parsed.get("patterns") or []))),
            "styles":        list(set((current_dislikes.get("styles") or [])        + (parsed.get("styles") or []))),
            "brands":        list(set((current_dislikes.get("brands") or [])        + (parsed.get("brands") or []))),
            "garment_types": list(set((current_dislikes.get("garment_types") or []) + (parsed.get("garment_types") or []))),
        }
        non_empty = {k: v for k, v in result.items() if v}
        if non_empty:
            logger.info(f"Negative preferences updated: {non_empty}")
        return result
    except Exception as exc:
        logger.warning(f"Negative feature extraction parse error: {exc}")
        return current_dislikes


# ─────────────────────────────────────────────────────────────────────────────
# Feature 6 — Result Explanation Helper
# ─────────────────────────────────────────────────────────────────────────────

def _build_match_reason(product: dict, features: FashionFeatures) -> str:
    """
    Rule-based 'why this product' explanation — no extra Gemini call.
    Compares product text against the user's known preferences.
    """
    title = (product.get("title") or "").lower()
    desc  = (product.get("description") or "").lower()
    text  = f"{title} {desc}"
    reasons: List[str] = []

    if features.garment_type and features.garment_type.lower() in text:
        reasons.append(features.garment_type)
    if features.color:
        matched = [c for c in features.color if c.lower() in text]
        if matched:
            reasons.append(matched[0])
    if features.style and features.style.lower() in text:
        reasons.append(f"{features.style} style")
    if features.occasion and features.occasion.lower() in text:
        reasons.append(f"{features.occasion}")
    if features.fabric and features.fabric.lower() in text:
        reasons.append(f"{features.fabric} fabric")
    price = product.get("price")
    if price and features.max_price and float(price) <= features.max_price:
        reasons.append("within budget")

    if reasons:
        return "Matches: " + ", ".join(reasons[:4])

    # Score-based fallback
    score = product.get("llm_score")
    if score and score >= 8:  return "Strong match"
    if score and score >= 6:  return "Good match"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Feature 4 — Outfit Completion Constants
# ─────────────────────────────────────────────────────────────────────────────

# Keywords that signal the user already knows what TYPE of complement they want
_COMPLEMENT_KEYWORDS: Dict[str, List[str]] = {
    "footwear":    ["shoes", "sandals", "heels", "juttis", "mojaris", "flats", "boots",
                    "footwear", "slippers", "kolhapuri", "wedges", "sneakers", "loafers"],
    "accessories": ["earrings", "necklace", "bag", "clutch", "dupatta", "jewellery",
                    "jewelry", "accessories", "bracelet", "bangles", "scarf", "belt", "watch"],
    "bottom":      ["palazzo", "churidar", "leggings", "salwar", "skirt", "trouser",
                    "pants", "bottom", "pant"],
    "top":         ["blouse", "top", "shirt", "kurti", "crop"],
}


def _detect_complement_type(msg: str) -> Optional[str]:
    """Return the complement category if the user's message names a specific item type."""
    m = msg.lower()
    for ctype, keywords in _COMPLEMENT_KEYWORDS.items():
        if any(kw in m for kw in keywords):
            return ctype
    return None


def _detect_complement_item(msg: str) -> Optional[str]:
    """
    Return the SPECIFIC item keyword the user mentioned (e.g. 'watch', 'heels', 'dupatta')
    rather than just the broad category ('accessories', 'footwear').
    Used by the ReAct subgraph so queries say 'watch for kurta' not 'accessories for kurta'.
    """
    m = msg.lower()
    for _ctype, keywords in _COMPLEMENT_KEYWORDS.items():
        for kw in keywords:
            if kw in m:
                return kw
    return None


_OUTFIT_COMPLEMENTS: Dict[str, List[str]] = {
    "kurta":    ["churidar", "palazzo pants", "leggings", "dupatta", "ethnic juttis"],
    "shirt":    ["chinos", "formal trousers", "blazer", "suit pants"],
    "dress":    ["heels", "sandals", "belt", "clutch bag", "cardigan"],
    "jeans":    ["top", "t-shirt", "sneakers", "jacket", "casual shirt"],
    "saree":    ["blouse", "heels", "clutch", "statement earrings"],
    "lehenga":  ["blouse", "heels", "statement earrings", "clutch"],
    "suit":     ["tie", "formal shoes", "pocket square", "belt"],
    "top":      ["jeans", "skirt", "straight trousers", "sneakers"],
    "jacket":   ["jeans", "t-shirt", "sneakers", "chinos"],
    "blazer":   ["formal shirt", "trousers", "formal shoes"],
    "skirt":    ["top", "blouse", "heels", "sneakers"],
    "palazzo":  ["kurta", "crop top", "embroidered top"],
}


# ─────────────────────────────────────────────────────────────────────────────
# ReAct Outfit Subgraph — 5 nodes + router + builder
# ─────────────────────────────────────────────────────────────────────────────

def oa_extract_attributes(state: OutfitState) -> OutfitState:
    """
    ReAct Step 0 — Extract visual/style attributes from the reference product.
    These are fed into subsequent query-generation steps for accurate matching.
    """
    ref = state.get("reference_product", {})
    title = ref.get("title", "")
    desc = (ref.get("description") or "").strip()
    text = f"{title}. {desc}".strip()

    if not text:
        logger.warning("ReAct outfit: no reference product — skipping attribute extraction")
        return {**state, "reference_attributes": {}}

    attributes: dict = {}

    if llm_service.is_enabled:
        prompt = (
            "Extract fashion attributes from this product for outfit coordination.\n"
            f"Product: {text}\n\n"
            "Return a JSON object (no markdown) with these fields:\n"
            "{\n"
            '  "garment_type": "kurta/dress/jeans/saree/etc or null",\n'
            '  "color": "primary color or null",\n'
            '  "secondary_colors": ["list", "of", "accent", "colors"] or [],\n'
            '  "style": "ethnic/casual/formal/boho/western/party or null",\n'
            '  "pattern": "solid/floral/embroidered/printed/etc or null",\n'
            '  "occasion": "wedding/casual/festival/office/etc or null",\n'
            '  "fabric": "cotton/silk/linen/etc or null"\n'
            "}\n"
            "Return ONLY the JSON."
        )
        raw = _gemini_call(prompt)
        if raw:
            try:
                attributes = json.loads(_clean_json(raw))
            except Exception as exc:
                logger.warning(f"ReAct outfit attribute parse error: {exc}")

    if not attributes:
        # Keyword fallback
        text_lower = text.lower()
        for color in ["red","blue","green","yellow","pink","black","white","orange",
                      "purple","beige","maroon","navy","cream","golden","grey","brown"]:
            if color in text_lower:
                attributes["color"] = color
                break
        for style in ["ethnic","casual","formal","boho","western","party","traditional"]:
            if style in text_lower:
                attributes["style"] = style
                break

    logger.info(f"ReAct outfit: attributes extracted from '{title[:50]}': {attributes}")
    return {**state, "reference_attributes": attributes}


def oa_generate_query(state: OutfitState) -> OutfitState:
    """
    ReAct — Reason step: generate a targeted web search query.
    Incorporates refinement_hints from failed previous iterations to avoid repeating mistakes.
    """
    ref_attrs        = state.get("reference_attributes", {})
    complement_type  = state.get("complement_type", "accessories")
    # Use the specific item the user asked for (e.g. "watch") over the broad category ("accessories")
    complement_item  = state.get("complement_item", "") or complement_type
    ref_product      = state.get("reference_product", {})
    refinement_hints = state.get("refinement_hints", [])
    iteration        = state.get("iteration", 0)
    user_gender      = state.get("user_gender", "")
    user_budget      = state.get("user_budget")

    ref_title  = ref_product.get("title", "")
    garment    = ref_attrs.get("garment_type", "")
    color      = ref_attrs.get("color", "")
    style      = ref_attrs.get("style", "ethnic")
    occasion   = ref_attrs.get("occasion", "")

    if llm_service.is_enabled:
        hint_text   = ""
        if refinement_hints:
            hint_text = (
                "\nPrevious attempts that did NOT work well:\n"
                + "\n".join(f"- {h}" for h in refinement_hints[-3:])
                + "\nGenerate a DIFFERENT query that avoids the issues listed above."
            )
        budget_text = f"\nBudget: under ₹{int(user_budget)}" if user_budget else ""
        gender_text = f"\nFor: {user_gender}" if user_gender else ""

        prompt = (
            f"Generate a specific Indian fashion/shopping search query for '{complement_item}' "
            f"to pair with: '{ref_title}'.\n\n"
            f"IMPORTANT: The query MUST be specifically about '{complement_item}' — "
            f"do NOT generate queries about the garment itself or other items.\n\n"
            f"Reference item attributes:\n"
            f"- Garment type: {garment or 'unknown'}\n"
            f"- Primary color: {color or 'unknown'}\n"
            f"- Style: {style or 'unknown'}\n"
            f"- Occasion: {occasion or 'unknown'}\n"
            f"{gender_text}{budget_text}\n"
            f"{hint_text}\n"
            f"Iteration {iteration + 1} of 5.\n"
            "Return ONLY the search query (one line, no explanation, no quotes)."
        )
        query = _gemini_call(prompt)
        if query:
            query = query.strip().strip('"').strip("'")
        else:
            parts = [user_gender, color, style, complement_item]
            if garment:
                parts.append(f"for {garment}")
            query = " ".join(p for p in parts if p).strip()
    else:
        parts = [user_gender, color, style, complement_item]
        if garment:
            parts.append(f"for {garment}")
        query = " ".join(p for p in parts if p).strip()

    if not query:
        query = f"{complement_item} for {ref_title[:30]}"

    logger.info(f"ReAct outfit iter {iteration + 1}/5: query='{query[:80]}'")
    return {**state, "current_query": query}


def oa_search_web(state: OutfitState) -> OutfitState:
    """
    ReAct — Act step: web search for the current_query.
    Tries Gemini Grounding first; falls back to direct e-commerce search links.
    """
    query            = state.get("current_query", "")
    complement_type  = state.get("complement_type", "accessories")
    # Use the specific item ("watch") rather than the broad category ("accessories") in prompts
    complement_item  = state.get("complement_item", "") or complement_type

    if not query:
        return {**state, "web_results": []}

    web_results: List[dict] = []
    grounding_worked = False

    # Try Gemini Grounding
    if llm_service.is_enabled:
        try:
            from google.genai import types as genai_types

            grounding_prompt = (
                f"Find '{complement_item}' available to buy in India that match: {query}\n"
                "Requirements:\n"
                "- List 4-5 individual products with name, price, and direct buy link\n"
                f"- Products must be '{complement_item}' ONLY — NOT kurtas, shirts, or other clothing\n"
                "- Only return results from reliable Indian e-commerce or brand sites"
            )
            response = llm_service._client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=grounding_prompt,
                config=genai_types.GenerateContentConfig(
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
                ),
            )

            grounding_chunks = []
            try:
                meta = response.candidates[0].grounding_metadata
                if meta and meta.grounding_chunks:
                    for chunk in meta.grounding_chunks:
                        if chunk.web:
                            grounding_chunks.append({
                                "title":       chunk.web.title or "Product",
                                "url":         chunk.web.uri,
                                "snippet":     None,
                                "source_site": chunk.web.uri.split("/")[2] if chunk.web.uri else None,
                            })
            except Exception:
                pass

            if grounding_chunks:
                web_results = grounding_chunks[:5]
                grounding_worked = True
                logger.info(f"ReAct outfit grounding: {len(web_results)} results for '{complement_item}' iter {state.get('iteration',0)+1}")

        except Exception as exc:
            logger.warning(f"ReAct outfit grounding failed: {exc}")

    # Direct e-commerce links fallback
    if not grounding_worked:
        encoded  = urllib.parse.quote_plus(query)
        short_q  = query[:50]
        web_results = [
            {"title": f"Search on Ajio: {short_q}",     "url": f"https://www.ajio.com/search/?text={encoded}",            "source_site": "ajio.com"},
            {"title": f"Search on Myntra: {short_q}",   "url": f"https://www.myntra.com/search?rawQuery={encoded}",        "source_site": "myntra.com"},
            {"title": f"Search on Amazon: {short_q}",   "url": f"https://www.amazon.in/s?k={encoded}",                    "source_site": "amazon.in"},
            {"title": f"Search on Flipkart: {short_q}", "url": f"https://www.flipkart.com/search?q={encoded}",            "source_site": "flipkart.com"},
        ]
        logger.info(f"ReAct outfit: direct links fallback for '{query[:50]}'")

    return {**state, "web_results": web_results}


def oa_evaluate_results(state: OutfitState) -> OutfitState:
    """
    ReAct — Observation step: Gemini evaluates whether results match complement_type.
    Increments the iteration counter. Saves a refinement_hint when results are poor
    so the next oa_generate_query call can avoid the same mistake.
    """
    web_results      = state.get("web_results", [])
    query            = state.get("current_query", "")
    complement_type  = state.get("complement_type", "accessories")
    complement_item  = state.get("complement_item", "") or complement_type
    iteration        = state.get("iteration", 0)
    refinement_hints = list(state.get("refinement_hints", []))

    new_iteration = iteration + 1

    if not web_results:
        refinement_hints.append(f"Query '{query}' returned no results")
        return {
            **state,
            "iteration":          new_iteration,
            "evaluation":         "poor",
            "evaluation_reason":  "No results returned",
            "refinement_hints":   refinement_hints,
        }

    # If all results are plain direct links (no snippet/grounding) — accept as good.
    # We can't evaluate raw search URLs without actually visiting them.
    all_direct = all(
        r.get("source_site") and not r.get("snippet")
        for r in web_results
    )
    if all_direct:
        logger.info(f"ReAct outfit iter {new_iteration}: direct links only — accepting")
        return {
            **state,
            "iteration":         new_iteration,
            "evaluation":        "good",
            "evaluation_reason": "Direct e-commerce search links provided",
            "refinement_hints":  refinement_hints,
        }

    # Use Gemini to evaluate grounding results
    if llm_service.is_enabled:
        results_text = "\n".join(
            f"- {r.get('title','Unknown')} ({r.get('source_site','')})"
            for r in web_results[:5]
        )
        prompt = (
            f"Evaluate if these search results are good matches for '{complement_item}'.\n"
            f"Search query: '{query}'\n"
            f"Results:\n{results_text}\n\n"
            "Criteria:\n"
            f"1. Results should be '{complement_item}' ONLY — if kurtas/shirts/clothing appear instead of '{complement_item}', that is a MISMATCH\n"
            "2. Results should be relevant to the search query\n"
            "3. Results should be from reliable shopping sites\n\n"
            "Respond with JSON (no markdown):\n"
            '{"evaluation": "good|poor|mismatch", "reason": "brief explanation"}\n'
            "good     = results closely match query and are the correct item type\n"
            "poor     = results are somewhat relevant but not ideal\n"
            "mismatch = results are completely wrong category (e.g. clothing when watch was searched)\n"
            "Return ONLY the JSON."
        )
        raw = _gemini_call(prompt)
        evaluation = "good"
        reason     = "Results appear relevant"
        if raw:
            try:
                parsed     = json.loads(_clean_json(raw))
                evaluation = parsed.get("evaluation", "good")
                reason     = parsed.get("reason", "")
                if evaluation not in ("good", "poor", "mismatch"):
                    evaluation = "good"
            except Exception:
                pass

        if evaluation != "good":
            refinement_hints.append(f"Query '{query}' was {evaluation}: {reason}")

        logger.info(f"ReAct outfit iter {new_iteration}: eval={evaluation} | {reason[:60]}")
        return {
            **state,
            "iteration":         new_iteration,
            "evaluation":        evaluation,
            "evaluation_reason": reason,
            "refinement_hints":  refinement_hints,
        }
    else:
        # No Gemini — accept whatever we have
        return {
            **state,
            "iteration":         new_iteration,
            "evaluation":        "good",
            "evaluation_reason": "Accepted without AI evaluation",
            "refinement_hints":  refinement_hints,
        }


def oa_format_response(state: OutfitState) -> OutfitState:
    """
    Generate the final outfit completion response text and select best web results.
    Apologises gracefully if max iterations were reached without a perfect match.
    """
    web_results     = state.get("web_results", [])
    complement_type = state.get("complement_type", "accessories")
    complement_item = state.get("complement_item", "") or complement_type
    ref_product     = state.get("reference_product", {})
    ref_attrs       = state.get("reference_attributes", {})
    iteration       = state.get("iteration", 0)
    evaluation      = state.get("evaluation", "good")

    ref_title  = ref_product.get("title", "your outfit")
    ref_color  = ref_attrs.get("color", "")
    ref_style  = ref_attrs.get("style", "")

    if llm_service.is_enabled:
        style_ctx = f"{ref_color} {ref_style}".strip() or "your style"

        if iteration >= 5 and evaluation != "good":
            prompt = (
                f"You searched 5 times for '{complement_item}' to pair with '{ref_title}' "
                "but couldn't find a perfect match online. Write a short, honest but encouraging response.\n"
                "Mention you found some search links they can explore manually. "
                "Suggest trying more specific search terms. "
                "Keep it under 3 sentences. Return ONLY the reply text."
            )
        else:
            prompt = (
                f"You found online results for '{complement_item}' to pair with '{ref_title}' ({style_ctx}).\n"
                f"Found {len(web_results)} links. Write a short enthusiastic response (2-3 sentences).\n"
                f"Mention the specific item ('{complement_item}') and the style connection.\n"
                "Do NOT describe or predict the link contents — just say you found links to explore.\n"
                "Return ONLY the reply text."
            )

        response_text = _gemini_call(prompt)
        if not response_text:
            response_text = (
                f"I found some {complement_item} options that should pair beautifully with your "
                f"{ref_style or ''} outfit! Here are some links to explore online."
            )
    else:
        response_text = (
            f"Here are some {complement_item} options to complement your look! "
            "Check these links to find what suits you best."
        )

    logger.info(f"ReAct outfit complete | iterations={iteration} | eval={evaluation} | {len(web_results)} links")
    return {**state, "outfit_response": response_text, "outfit_web_results": web_results}


def _outfit_react_router(state: OutfitState) -> str:
    """
    ReAct loop router:
      good result OR max iterations reached → format response
      poor/mismatch + iterations remaining  → refine query and try again
    """
    evaluation = state.get("evaluation", "poor")
    iteration  = state.get("iteration", 0)

    if evaluation == "good":
        logger.info(f"ReAct outfit: accepted at iteration {iteration}")
        return "oa_format_response"
    elif iteration >= 5:
        logger.info(f"ReAct outfit: max 5 iterations reached — formatting best-effort response")
        return "oa_format_response"
    else:
        logger.info(f"ReAct outfit: iter {iteration} eval={evaluation} — refining query")
        return "oa_generate_query"


def _build_outfit_subgraph():
    """Compile the ReAct outfit completion subgraph."""
    graph = StateGraph(OutfitState)

    graph.add_node("oa_extract_attributes", oa_extract_attributes)
    graph.add_node("oa_generate_query",     oa_generate_query)
    graph.add_node("oa_search_web",         oa_search_web)
    graph.add_node("oa_evaluate_results",   oa_evaluate_results)
    graph.add_node("oa_format_response",    oa_format_response)

    # Linear first pass
    graph.add_edge(START,                   "oa_extract_attributes")
    graph.add_edge("oa_extract_attributes", "oa_generate_query")
    graph.add_edge("oa_generate_query",     "oa_search_web")
    graph.add_edge("oa_search_web",         "oa_evaluate_results")

    # ReAct loop
    graph.add_conditional_edges(
        "oa_evaluate_results",
        _outfit_react_router,
        {
            "oa_generate_query":  "oa_generate_query",
            "oa_format_response": "oa_format_response",
        },
    )

    graph.add_edge("oa_format_response", END)
    return graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Node 1 — Classify Intent
# ─────────────────────────────────────────────────────────────────────────────

def classify_intent(state: ChatState) -> ChatState:
    """
    Gemini reads the last message + conversation history and classifies intent into:
      new_search       — user wants to find new products
      refine           — user wants to modify the previous search (colour, price, etc.)
      feedback_positive — user liked the results
      feedback_negative — user disliked the results
      general          — greeting, meta question, no search needed
    """
    last_msg = _get_last_user_message(state.get("messages", []))

    # ── Pre-check: marketplace-specific request → skip local DB entirely ──
    marketplace = _detect_marketplace(last_msg)
    if marketplace:
        logger.info(f"Intent classified: marketplace_search ({marketplace})")
        return {**state, "intent": "marketplace_search", "target_marketplace": marketplace}

    if not llm_service.is_enabled:
        intent = _keyword_intent(last_msg)
        logger.info(f"Intent classified (keyword fallback): {intent}")
        return {**state, "intent": intent, "target_marketplace": ""}

    history = _format_history(state.get("messages", []))

    prompt = (
        "You are an AI fashion shopping assistant. Classify the user's latest message intent.\n\n"
        f"Conversation history:\n{history}\n\n"
        "Classify the intent into ONE of these categories:\n"
        "- new_search: user wants to find new/different products\n"
        "- refine: user wants to modify previous results (e.g. 'in red', 'under 500')\n"
        "- outfit_completion: user wants items that COMPLEMENT or GO WITH something they saw/have "
        "  (e.g. 'what goes with this kurta', 'pair it with', 'what to wear with', 'complete the look')\n"
        "- feedback_positive: user liked/approved the results ('love it', 'great', 'nice')\n"
        "- feedback_negative: user disliked results ('don't like', 'not what I wanted', 'show something else')\n"
        "- general: greeting, question about the bot, 'what did you do', 'thanks', etc.\n\n"
        "Return ONLY the category name, nothing else."
    )

    result = _gemini_call(prompt)
    valid = {"new_search", "refine", "outfit_completion", "feedback_positive", "feedback_negative", "general"}
    if result and result.strip().lower() in valid:
        intent = result.strip().lower()
    else:
        # Gemini failed or returned invalid value — use keyword fallback
        intent = _keyword_intent(last_msg)
        logger.info(f"Gemini intent failed — keyword fallback: {intent}")

    logger.info(f"Intent classified: {intent}")
    return {**state, "intent": intent, "target_marketplace": ""}


# ─────────────────────────────────────────────────────────────────────────────
# Node 2 — Extract Fashion Features  ⭐ Core new node
# ─────────────────────────────────────────────────────────────────────────────

def extract_fashion_features(state: ChatState) -> ChatState:
    """
    Dedicated Gemini node that extracts structured outfit attributes from the
    conversation. Merges them with accumulated session preferences so that
    attributes like gender/budget persist across turns even when not mentioned.

    Also builds the CLIP query string and FAISS filter dict for the search.
    """
    last_msg = _get_last_user_message(state.get("messages", []))
    image_desc = state.get("image_description")
    history = _format_history(state.get("messages", []))
    accumulated = state.get("user_preferences", {})

    # Context for Gemini includes image description if present
    input_context = last_msg
    if image_desc:
        input_context = f"[Image described as: {image_desc}]\nUser says: {last_msg}"

    if llm_service.is_enabled:
        prompt = (
            "You are a fashion AI. Extract structured product attributes from the conversation.\n\n"
            f"Conversation:\n{history}\n\n"
            f"Current input: {input_context}\n\n"
            "Extract ONLY the attributes EXPLICITLY mentioned or clearly implied. "
            "Return a JSON object (no markdown) with these keys (set to null if not mentioned):\n"
            "{\n"
            '  "garment_type": "kurta|dress|jeans|top|saree|jacket|shirt|etc or null",\n'
            '  "color": ["list", "of", "colors"] or null,\n'
            '  "pattern": "floral|solid|striped|embroidered|printed|etc or null",\n'
            '  "style": "ethnic|casual|formal|boho|western|party|etc or null",\n'
            '  "fit": "slim|regular|relaxed|oversized|etc or null",\n'
            '  "fabric": "cotton|silk|denim|linen|etc or null",\n'
            '  "occasion": "wedding|casual|office|beach|festival|etc or null",\n'
            '  "gender": "men|women or null",\n'
            '  "max_price": number or null,\n'
            '  "min_price": number or null,\n'
            '  "brand": "CLOTHING brand name only (e.g. Zara, Fabindia, H&M, Manyavar) or null. '
            'IMPORTANT: e-commerce platforms are NOT brands — set null for: '
            'flipkart, amazon, myntra, ajio, meesho, nykaa, snapdeal, tata cliq",\n'
            '  "sleeve_type": "full|half|sleeveless|puffed|etc or null",\n'
            '  "neckline": "mandarin|round|v-neck|sweetheart|etc or null"\n'
            "}\n"
            "Return ONLY the JSON object."
        )

        raw = _gemini_call(prompt)
        if raw:
            try:
                parsed = json.loads(_clean_json(raw))
                current_features = FashionFeatures(**{
                    k: v for k, v in parsed.items()
                    if k in FashionFeatures.model_fields
                })
            except Exception as exc:
                logger.warning(f"Feature extraction parse error: {exc}")
                current_features = FashionFeatures()
        else:
            current_features = FashionFeatures()
    else:
        # Fallback: treat raw message as query, no structured extraction
        current_features = FashionFeatures()

    # Merge with accumulated session preferences — with category-switch detection
    accumulated_features = FashionFeatures(**accumulated) if accumulated else FashionFeatures()
    intent = state.get("intent", "new_search")

    old_garment = (accumulated_features.garment_type or "").lower()
    new_garment = (current_features.garment_type or "").lower()
    category_switched = (
        intent == "new_search"
        and new_garment
        and old_garment
        and new_garment != old_garment
    )

    if category_switched:
        # User is searching for a completely different product type (e.g. shirt → ring).
        # Reset all product-specific attributes; only keep cross-category ones (gender, budget).
        base = FashionFeatures(
            gender=accumulated_features.gender,
            max_price=accumulated_features.max_price,
            min_price=accumulated_features.min_price,
        )
        merged = base.merge(current_features)
        logger.info(
            f"Category switch detected ({old_garment} → {new_garment}) — "
            "product-specific preferences reset"
        )
    else:
        merged = accumulated_features.merge(current_features)

    # Build CLIP query — prefer merged features, fall back to raw message
    clip_query = merged.to_clip_query()
    if not clip_query:
        clip_query = llm_service.expand_query(last_msg) if llm_service.is_enabled else last_msg

    search_params = SearchParams(
        query=clip_query,
        filters=merged.to_filters(),
        k=12,
    )

    # Feature 2 — Slot Filling: compute which critical attributes are still missing
    missing_slots = _compute_missing_slots(merged)

    logger.info(
        f"Features extracted | query='{clip_query[:60]}' | "
        f"filters={search_params.filters} | missing_slots={missing_slots}"
    )

    return {
        **state,
        "current_features": current_features.model_dump(),
        "user_preferences": merged.model_dump(),
        "search_params": search_params.model_dump(),
        "missing_slots": missing_slots,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 3 — Search Local DB
# ─────────────────────────────────────────────────────────────────────────────

def search_local_db(state: ChatState) -> ChatState:
    """
    Feature 5 — Parallel Search: runs two FAISS queries simultaneously using threads.
      • Primary query  : Gemini-extracted structured CLIP features (precise)
      • Secondary query: Raw user message (broader recall, different angle)
    Results are merged and deduplicated by product ID before re-ranking.

    Feature 1 — Negative Filtering: products matching disliked attributes are removed
    from merged results (fallback: keep all if filtering removes everything).
    """
    params_dict = state.get("search_params", {})
    params = SearchParams(**params_dict) if params_dict else SearchParams(query="")

    if not params.query or not search_engine.is_ready():
        logger.warning("Search engine not ready or empty query")
        return {**state, "local_results": []}

    primary_results: List[dict] = []
    secondary_results: List[dict] = []

    def _run_primary():
        nonlocal primary_results
        primary_results = search_engine.search_by_text(
            query=params.query,
            k=params.k,
            filters=params.filters if params.filters else None,
        )

    def _run_secondary():
        nonlocal secondary_results
        raw_query = state.get("raw_query", "").strip()
        # Only run secondary if the raw query is meaningfully different from primary
        if raw_query and raw_query.lower() != params.query.lower():
            secondary_results = search_engine.search_by_text(
                query=raw_query,
                k=8,
                filters=None,   # No filters — broader recall
            )

    # ── Parallel execution ────────────────────────────────────────────────
    t1 = threading.Thread(target=_run_primary,   daemon=True)
    t2 = threading.Thread(target=_run_secondary, daemon=True)
    t1.start(); t2.start()
    t1.join();  t2.join()

    # ── Merge & deduplicate ───────────────────────────────────────────────
    seen: Dict[str, dict] = {}
    for p in primary_results + secondary_results:
        pid = str(p.get("id", ""))
        if pid and pid not in seen:
            seen[pid] = p
    merged = list(seen.values())

    # ── Feature 1: Negative filtering ────────────────────────────────────
    disliked = state.get("disliked_features", {})
    if disliked and merged:
        filtered = []
        for product in merged:
            title = (product.get("title") or "").lower()
            desc  = (product.get("description") or "").lower()
            text  = f"{title} {desc}"
            skip  = False
            for field in ("colors", "patterns", "styles", "brands", "garment_types"):
                for val in (disliked.get(field) or []):
                    if val.lower() in text:
                        skip = True
                        break
                if skip:
                    break
            if not skip:
                filtered.append(product)
        if filtered:   # Only apply filter when it doesn't wipe everything out
            logger.info(f"Negative filter: {len(merged)} → {len(filtered)} products")
            merged = filtered

    logger.info(
        f"Parallel search | primary={len(primary_results)} "
        f"secondary={len(secondary_results)} unique={len(merged)}"
    )
    return {**state, "local_results": merged}


# ─────────────────────────────────────────────────────────────────────────────
# Node 4 — Rerank Results
# ─────────────────────────────────────────────────────────────────────────────

def rerank_results_node(state: ChatState) -> ChatState:
    """
    Re-rank local results using Gemini.
    Uses the original user message + extracted features as scoring criteria
    (not just the expanded CLIP query) for better relevance judgment.
    """
    local_results = state.get("local_results", [])
    if not local_results:
        return {**state, "final_results": [], "results_quality": "empty"}

    # Use original user query for re-ranking (not the expanded CLIP query)
    rerank_query = _get_last_user_message(state.get("messages", []))

    # Feature 3 — Personalized Re-ranking: inject full accumulated user preferences
    user_prefs = FashionFeatures(**state.get("user_preferences", {}))
    pref_context = user_prefs.to_clip_query()
    if pref_context:
        rerank_query = f"{rerank_query} | User preferences: {pref_context}"

    # Feature 1 — Negative context: tell re-ranker what to penalise
    disliked = state.get("disliked_features", {})
    dislikes: List[str] = []
    for field in ("colors", "patterns", "styles"):
        vals = disliked.get(field) or []
        if vals:
            dislikes.append(f"avoid {field}: {', '.join(vals)}")
    if dislikes:
        rerank_query = f"{rerank_query} | AVOID: {'; '.join(dislikes)}"

    final = llm_service.rerank_results(rerank_query, local_results)

    # Feature 6 — Result Explanation: add match_reason to every product (rule-based, free)
    for r in final:
        r["match_reason"] = _build_match_reason(r, user_prefs)

    all_scores_null = all(r.get("llm_score") is None for r in final)
    best_score = max(
        (r.get("llm_score") or 0 for r in final),
        default=0,
    )

    if all_scores_null and final:
        # Gemini scoring unavailable (quota exhausted, etc.) — show CLIP results directly
        # rather than routing to web search. CLIP similarity is a good enough proxy.
        quality = "good"
    elif best_score >= 6:
        quality = "good"
    elif best_score >= 3:
        quality = "mediocre"
    elif final:
        quality = "poor"
    else:
        quality = "empty"

    logger.info(
        f"Rerank complete | quality={quality} | best_score={best_score} "
        f"| gemini_scored={not all_scores_null}"
    )
    return {**state, "final_results": final, "results_quality": quality}


# ─────────────────────────────────────────────────────────────────────────────
# Conditional Edge — Quality Router
# ─────────────────────────────────────────────────────────────────────────────

def quality_router(state: ChatState) -> str:
    quality = state.get("results_quality", "empty")
    if quality == "good":
        return "generate_response"
    elif quality == "mediocre":
        return "clarification_check"
    else:
        return "web_search"


# ─────────────────────────────────────────────────────────────────────────────
# Conditional Edge — Clarification Router
# ─────────────────────────────────────────────────────────────────────────────

def clarification_router(state: ChatState) -> str:
    count = state.get("clarification_count", 0)
    if count >= 2:
        logger.info("Clarification limit reached — routing to web search")
        return "web_search"
    return "ask_clarification"


# ─────────────────────────────────────────────────────────────────────────────
# Node 5 — Ask Clarification
# ─────────────────────────────────────────────────────────────────────────────

def ask_clarification(state: ChatState) -> ChatState:
    """
    Feature 2 — Slot Filling: uses the pre-computed missing_slots list to ask
    the single most important missing question rather than a generic prompt.
    Questions are prioritised: garment_type → gender → occasion → budget → color.
    """
    history     = _format_history(state.get("messages", []))
    count       = state.get("clarification_count", 0)
    missing_slots = state.get("missing_slots", [])

    # Human-readable slot questions (for Gemini hint + fallback)
    _slot_prompts: Dict[str, str] = {
        "garment_type": "What type of clothing are you looking for? (e.g. kurta, dress, jeans, shirt)",
        "gender":       "Is this for men or women?",
        "occasion":     "What's the occasion? (casual, wedding, office, party, festival…)",
        "budget":       "What's your budget or price range?",
        "color":        "Do you have a color preference?",
    }

    top_slot     = missing_slots[0] if missing_slots else None
    slot_hint    = f"Most important missing info: {_slot_prompts.get(top_slot, top_slot)}" if top_slot else ""

    if llm_service.is_enabled:
        prompt = (
            "You are a helpful fashion assistant. "
            "The search didn't find great matches. Ask ONE short, friendly question "
            "to help narrow the search.\n\n"
            f"Conversation so far:\n{history}\n\n"
            f"{slot_hint}\n\n"
            "Ask only ONE question. Keep it conversational. Return ONLY the question."
        )
        question = _gemini_call(prompt)
        if not question:
            question = (_slot_prompts.get(top_slot, "Could you tell me more about the style or occasion?")
                        if top_slot else "Could you tell me more about the style or occasion?")
    else:
        question = (_slot_prompts.get(top_slot, "Could you tell me more about what you're looking for?")
                    if top_slot else "Could you tell me more about what you're looking for?")

    new_count = count + 1
    logger.info(f"Slot clarification #{new_count} | top_slot={top_slot} | {question[:60]}")

    return {
        **state,
        "response": question,
        "clarification_count": new_count,
        "products_to_show": [],
        "web_results": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 6 — Handle Feedback
# ─────────────────────────────────────────────────────────────────────────────

def handle_feedback_node(state: ChatState) -> ChatState:
    """
    Classifies user feedback into one of:
      wants_refinement  — change one attribute (colour, price, style)
      wants_different   — completely different products
      just_positive     — liked results, no action needed
      very_unsatisfied  — frustrated, force web search
    """
    last_msg = _get_last_user_message(state.get("messages", []))
    history = _format_history(state.get("messages", []))

    if not llm_service.is_enabled:
        return {**state, "feedback_action": "wants_refinement"}

    prompt = (
        "Classify this user's feedback about fashion product recommendations.\n\n"
        f"Conversation:\n{history}\n\n"
        "Categories (pick EXACTLY one):\n"
        "- wants_refinement: user wants ONE small attribute changed but likes the general direction "
        "  (e.g. 'in red instead', 'cheaper ones', 'different style', 'without embroidery')\n"
        "- wants_different: user is not satisfied and wants completely different products or a fresh start "
        "  (e.g. 'not satisfied', 'I don\\'t like these', 'show me something else', 'these are not good', "
        "  'not what I wanted', 'show different ones')\n"
        "- just_positive: user is happy, no action needed ('love it', 'great', 'nice', 'perfect')\n"
        "- very_unsatisfied: user is frustrated or angry ('hate these', 'completely wrong', 'useless', 'terrible')\n\n"
        "IMPORTANT: 'not satisfied', 'I don\\'t like', 'show something else' → wants_different (NOT wants_refinement)\n"
        "Return ONLY the category name, nothing else."
    )

    result = _gemini_call(prompt)
    valid = {"wants_refinement", "wants_different", "just_positive", "very_unsatisfied"}
    action = result.strip().lower() if result else "wants_refinement"
    if action not in valid:
        action = "wants_refinement"

    logger.info(f"Feedback classified: {action}")

    # Feature 1 — Negative Preference Memory: extract dislikes on any non-positive feedback
    updated_dislikes = state.get("disliked_features", {})
    if action != "just_positive":
        updated_dislikes = _extract_negative_features(last_msg, updated_dislikes)

    return {**state, "feedback_action": action, "disliked_features": updated_dislikes}


# ─────────────────────────────────────────────────────────────────────────────
# Conditional Edge — Feedback Router
# ─────────────────────────────────────────────────────────────────────────────

def feedback_router(state: ChatState) -> str:
    action = state.get("feedback_action", "wants_refinement")
    if action == "wants_refinement":
        # Small attribute tweak (colour, price) — try local DB first
        return "extract_fashion_features"
    elif action == "just_positive":
        return "generate_response"
    else:
        # wants_different / very_unsatisfied → go to e-commerce web search
        # User is dissatisfied with local results; show them real shopping links
        return "web_search"


# ─────────────────────────────────────────────────────────────────────────────
# Node 7A — Outfit Completion  (Feature 4)
# ─────────────────────────────────────────────────────────────────────────────

def outfit_completion_node(state: ChatState) -> ChatState:
    """
    Feature 4 — Outfit Completion with ReAct Agentic Subgraph.

    Turn 1 (complement type unknown):
        Asks "what type of item — footwear / accessories / bottom?"
        Sets awaiting_outfit_detail=True and returns immediately (waits for user).

    Turn 2 (complement type known):
        Invokes the ReAct outfit subgraph (max 5 iterations):
          extract_attributes → generate_query → web_search → evaluate
          → (loop if poor, up to 5×) → format_response
        The subgraph searches ONLINE DIRECTLY (no local FAISS — not enough products).
        Sets response + web_results directly so graph routes straight to update_memory.
    """
    user_msg    = _get_last_user_message(state.get("messages", []))
    user_prefs  = FashionFeatures(**state.get("user_preferences", {}))
    outfit_ctx  = state.get("outfit_context", "")
    awaiting    = state.get("awaiting_outfit_detail", False)
    ref_product = state.get("last_shown_product", {})   # Full product dict

    # ── Identify reference garment ────────────────────────────────────────
    ref_garment = user_prefs.garment_type or ""
    ref_title   = (ref_product.get("title") if ref_product else None) or outfit_ctx or ref_garment
    if not ref_garment:
        for garment in _OUTFIT_COMPLEMENTS:
            if garment in (outfit_ctx or user_msg).lower():
                ref_garment = garment
                break

    # ── Step 1: Detect complement type + specific item from user's message ─
    complement_type = _detect_complement_type(user_msg)
    complement_item = _detect_complement_item(user_msg) or ""  # e.g. "watch", "heels", "dupatta"

    # ── Step 2: Type unknown on first call → ask clarifying question ──────
    if not complement_type and not awaiting:
        garment_label = ref_garment or "outfit"
        if llm_service.is_enabled:
            history = _format_history(state.get("messages", []))
            prompt = (
                f"A user wants outfit completion suggestions for their {garment_label}.\n"
                f"Conversation so far:\n{history}\n\n"
                "Ask them ONE friendly, specific question: what TYPE of item are they looking for?\n"
                "Give examples like: footwear (juttis/sandals/heels), accessories "
                "(dupatta/earrings/clutch), or bottom wear (palazzo/churidar/leggings).\n"
                "Keep it short and conversational. Return ONLY the question."
            )
            question = _gemini_call(prompt) or (
                f"I'd love to complete your {garment_label} look! What type of item are you looking for? "
                "Footwear (juttis/sandals/heels), accessories (dupatta/earrings/clutch), "
                "or bottom wear (palazzo/churidar/leggings)?"
            )
        else:
            question = (
                f"What type of item would you like to pair with the {garment_label}? "
                "Footwear, accessories, or bottom wear?"
            )

        logger.info(f"Outfit ReAct — asking complement type for ref='{garment_label}'")
        return {
            **state,
            "awaiting_outfit_detail": True,
            "response":         question,
            "products_to_show": [],
            "web_results":      [],
        }

    # ── Step 3: Type is known → run the ReAct subgraph ───────────────────
    type_label = complement_type or "accessories"   # fallback if second call but still vague
    # item_label: the specific item ("watch", "heels") or fall back to type_label
    item_label = complement_item or type_label

    logger.info(
        f"Outfit ReAct starting | ref='{(ref_title or 'unknown')[:50]}' | "
        f"item='{item_label}' | type='{type_label}' | max_iter=5"
    )

    outfit_state: OutfitState = {
        "reference_product":    ref_product,
        "reference_attributes": {},
        "complement_type":      type_label,
        "complement_item":      item_label,   # specific: "watch" / "heels" / "dupatta"
        "user_gender":          user_prefs.gender or "",
        "user_budget":          user_prefs.max_price,
        "iteration":            0,
        "current_query":        "",
        "refinement_hints":     [],
        "web_results":          [],
        "evaluation":           "",
        "evaluation_reason":    "",
        "outfit_response":      "",
        "outfit_web_results":   [],
    }

    if _outfit_agent is not None:
        try:
            outfit_result = _outfit_agent.invoke(outfit_state)
        except Exception as exc:
            logger.error(f"ReAct outfit subgraph error: {exc}")
            # Emergency fallback: single direct-link search
            outfit_result = oa_extract_attributes(outfit_state)
            outfit_result = oa_generate_query(outfit_result)
            outfit_result = oa_search_web(outfit_result)
            outfit_result["evaluation"] = "good"
            outfit_result["iteration"]  = 1
            outfit_result = oa_format_response(outfit_result)
    else:
        # LangGraph subgraph not compiled — run nodes sequentially as fallback
        outfit_result = oa_extract_attributes(outfit_state)
        outfit_result = oa_generate_query(outfit_result)
        outfit_result = oa_search_web(outfit_result)
        outfit_result["evaluation"] = "good"
        outfit_result["iteration"]  = 1
        outfit_result = oa_format_response(outfit_result)

    # Map ReAct results back into ChatState (skip generate_response — response already set)
    return {
        **state,
        "awaiting_outfit_detail": False,
        "response":              outfit_result.get("outfit_response", ""),
        "web_results":           outfit_result.get("outfit_web_results", []),
        "web_search_triggered":  True,
        "products_to_show":      [],
        "final_results":         [],
        "intent":                "outfit_completion",
        "last_search_query":     outfit_result.get("current_query", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 7B — Web Search (Direct Links — no Grounding)
# ─────────────────────────────────────────────────────────────────────────────

def _build_structured_web_query(
    features: FashionFeatures,
    last_search_query: str,
    fallback: str,
) -> str:
    """
    Build a gender-aware, occasion-specific web search query from structured features.
    Gender is placed FIRST so e-commerce platforms don't default to the wrong section.
    Format: "{gender} {garment_type} {color} {style} {occasion} under {budget}"
    """
    parts: List[str] = []
    if features.gender:
        parts.append(features.gender)          # "men" / "women" — MUST be first
    if features.garment_type:
        parts.append(features.garment_type)
    colors = features.color if isinstance(features.color, list) else ([features.color] if features.color else [])
    if colors:
        parts.append(colors[0])
    if features.style:
        parts.append(features.style)
    if features.occasion:
        parts.append(features.occasion)
    if features.max_price:
        parts.append(f"under {int(features.max_price)}")

    if len(parts) >= 2:
        return " ".join(p for p in parts if p).strip()
    # Features too sparse — fall back to last turn's actual search query
    return last_search_query or fallback


def web_search(state: ChatState) -> ChatState:
    """
    Generates targeted direct e-commerce search links for Indian fashion platforms.

    Gemini Grounding is intentionally NOT used — in practice it consistently returns
    non-fashion sites (gift shops, decor wholesalers, wedding return-gift stores) for
    any query that contains words like "wedding", "ethnic", "occasion", etc.

    Instead: Gemini generates good query *strings* (text-only) which are then encoded
    into direct search URLs for Myntra, Ajio, Amazon, Flipkart, and Meesho.
    Gender is always enforced in the query so "men kurta" never becomes just "kurta".
    """
    features           = FashionFeatures(**state.get("user_preferences", {}))
    last_search_query  = state.get("last_search_query", "")
    last_user_msg      = _get_last_user_message(state.get("messages", []))
    target_marketplace = state.get("target_marketplace", "")

    # ── Step 1: Build structured base query (gender-first) ────────────────
    # For outfit-complement searches, last_search_query is more accurate
    # (e.g. "ethnic sandals for kurta" vs user_preferences.garment_type = "kurta").
    structured_query = _build_structured_web_query(features, last_search_query, last_user_msg)
    pref_query = features.to_clip_query()
    if last_search_query and last_search_query.lower() != pref_query.lower():
        base_query = last_search_query        # outfit-complement query from previous turn
    else:
        base_query = structured_query         # structured: "men kurta ethnic wedding under 2000"

    # ── Step 2: Use Gemini to expand to 2 query variants (text only, no grounding) ──
    search_queries: List[str] = []
    if llm_service.is_enabled:
        gender_rule  = f"- EVERY query MUST start with '{features.gender}' — never drop the gender word." if features.gender else ""
        budget_rule  = f"- EVERY query MUST include 'under {int(features.max_price)}' or 'below {int(features.max_price)}'." if features.max_price else ""
        platform_ctx = f" for {target_marketplace}" if target_marketplace else " for Indian fashion e-commerce (Myntra/Ajio/Amazon/Flipkart)"
        feedback_ctx = (
            f"\nUser just said: '{last_user_msg}'\n"
            "If the user rejected previous results, generate queries for ALTERNATIVE items in the same category "
            "(e.g. if sandals were rejected, suggest juttis/mojaris/heels instead)."
        ) if last_user_msg else ""

        prompt = (
            f"Generate 2 search query variants to find this fashion item{platform_ctx}.\n"
            f"Base description: {base_query}\n\n"
            "Rules (STRICT):\n"
            f"{gender_rule}\n"
            f"{budget_rule}\n"
            "- Queries must be for CLOTHING or FASHION items only — never gifts, decor, or home items\n"
            "- Be specific: include garment type, key style/occasion attributes\n"
            "- Keep each query under 8 words\n"
            f"{feedback_ctx}\n"
            'Return ONLY a JSON array of 2 strings, e.g. ["men kurta wedding under 2000", "men ethnic kurta under 2000"]'
        )
        raw = _gemini_call(prompt)
        if raw:
            try:
                queries = json.loads(_clean_json(raw))
                search_queries = [str(q).strip() for q in queries[:2] if q]
            except Exception:
                pass

        # Safety: if Gemini dropped gender, force it back into every query
        if features.gender and search_queries:
            g = features.gender.lower()
            search_queries = [
                q if g in q.lower() else f"{features.gender} {q}"
                for q in search_queries
            ]

    if not search_queries:
        search_queries = [base_query]

    logger.info(f"Web search | queries={search_queries} | platform={target_marketplace or 'any'}")

    # ── Step 3: Build direct e-commerce search links ──────────────────────
    # Always use direct links — grounding is removed because it consistently
    # returns non-fashion sites (gift shops, decor wholesalers, etc.) for
    # queries containing words like "wedding", "ethnic", or "occasion".
    raw_q   = search_queries[0]
    encoded = urllib.parse.quote_plus(raw_q)
    short_q = raw_q[:55]

    # Platform URL templates (all verified search endpoints)
    platform_urls = {
        "flipkart": ("Flipkart",      f"https://www.flipkart.com/search?q={encoded}",                          "flipkart.com"),
        "amazon":   ("Amazon",        f"https://www.amazon.in/s?k={encoded}",                                  "amazon.in"),
        "myntra":   ("Myntra",        f"https://www.myntra.com/search?rawQuery={encoded}",                     "myntra.com"),
        "ajio":     ("Ajio",          f"https://www.ajio.com/search/?text={encoded}",                          "ajio.com"),
        "meesho":   ("Meesho",        f"https://www.meesho.com/search?q={encoded}",                            "meesho.com"),
        "nykaa":    ("Nykaa Fashion", f"https://www.nykaafashion.com/search?q={encoded}",                      "nykaafashion.com"),
        "snapdeal": ("Snapdeal",      f"https://www.snapdeal.com/search?keyword={encoded}",                    "snapdeal.com"),
        "tatacliq": ("Tata CLiQ",     f"https://www.tatacliq.com/search/?searchCategory=all&text={encoded}",   "tatacliq.com"),
    }

    if target_marketplace and target_marketplace in platform_urls:
        # User asked for a specific platform — show it first, then top-3 others
        ordered = [target_marketplace] + [k for k in ["myntra", "ajio", "amazon", "flipkart"] if k != target_marketplace]
        direct_links = []
        for key in ordered[:4]:
            if key in platform_urls:
                n, u, s = platform_urls[key]
                direct_links.append(WebSearchResult(title=f"Search on {n}: {short_q}", url=u, source_site=s))
        logger.info(f"Platform-specific links for: {target_marketplace}")
    else:
        # Default order: fashion-dedicated platforms first (better category filters),
        # then general marketplaces. 5 links total for good coverage.
        direct_links = [
            WebSearchResult(title=f"Myntra — {short_q}",   url=platform_urls["myntra"][1],   source_site="myntra.com"),
            WebSearchResult(title=f"Ajio — {short_q}",     url=platform_urls["ajio"][1],     source_site="ajio.com"),
            WebSearchResult(title=f"Amazon — {short_q}",   url=platform_urls["amazon"][1],   source_site="amazon.in"),
            WebSearchResult(title=f"Flipkart — {short_q}", url=platform_urls["flipkart"][1], source_site="flipkart.com"),
            WebSearchResult(title=f"Meesho — {short_q}",   url=platform_urls["meesho"][1],   source_site="meesho.com"),
        ]

    web_results = [r.model_dump() for r in direct_links]
    logger.info(f"Direct links | query='{raw_q[:60]}' | {len(web_results)} platforms")

    return {
        **state,
        "web_search_triggered": True,
        "search_queries":       search_queries,
        "web_results":          web_results,
        "final_results":        [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Feature Suggestion Helper
# ─────────────────────────────────────────────────────────────────────────────

# Attributes to suggest, ordered by usefulness, keyed by garment category
_GARMENT_SUGGESTIONS: Dict[str, List[str]] = {
    "ring":      ["metal (gold/silver/rose gold)", "gemstone type", "occasion (casual/wedding)"],
    "necklace":  ["metal (gold/silver)", "length", "occasion"],
    "bracelet":  ["material", "occasion", "style (minimal/statement)"],
    "earring":   ["style (stud/hoop/drop)", "metal", "occasion"],
    "watch":     ["strap type (leather/metal)", "dial color", "occasion"],
    "kurta":     ["color", "fabric (cotton/silk)", "sleeve length"],
    "dress":     ["color", "occasion", "length (mini/midi/maxi)"],
    "shirt":     ["color", "fabric (cotton/linen)", "fit (slim/regular)"],
    "jeans":     ["color (blue/black/grey)", "fit (slim/straight/wide leg)"],
    "saree":     ["fabric (silk/cotton/georgette)", "color", "occasion"],
    "jacket":    ["color", "material (denim/leather/wool)", "occasion"],
    "top":       ["color", "sleeve style", "neckline"],
    "lehenga":   ["color", "fabric", "occasion (wedding/festival)"],
    "suit":      ["color", "fabric", "fit"],
}
_DEFAULT_SUGGESTIONS = ["color preference", "budget/price range", "occasion"]


def _build_feature_suggestion(features: FashionFeatures) -> Optional[str]:
    """
    Return a short suggestion string for attributes the user hasn't specified yet.
    Returns None when most key attributes are already filled.
    """
    garment = (features.garment_type or "").lower()

    # Pick the suggestion list for this garment, or default
    candidates = _GARMENT_SUGGESTIONS.get(garment, _DEFAULT_SUGGESTIONS)

    # Check which ones are already covered
    covered = set()
    if features.color:     covered.add("color")
    if features.max_price or features.min_price: covered.add("budget")
    if features.occasion:  covered.add("occasion")
    if features.fabric:    covered.add("fabric")
    if features.style:     covered.add("style")
    if features.fit:       covered.add("fit")
    if features.brand:     covered.add("brand")

    missing = [c for c in candidates if not any(cov in c for cov in covered)]

    if len(missing) >= 2:
        return f"💡 Want more precise results? Try specifying: {missing[0]} or {missing[1]}."
    elif len(missing) == 1:
        return f"💡 You can also specify: {missing[0]} for better matches."
    return None  # Everything is well-specified, no suggestion needed


# ─────────────────────────────────────────────────────────────────────────────
# Node 8 — Generate Response
# ─────────────────────────────────────────────────────────────────────────────

def generate_response(state: ChatState) -> ChatState:
    """
    Gemini writes a contextual, friendly fashion assistant reply.
    Tone adapts: excited for good results, helpful for web results,
    apologetic for no results, conversational for general intent.
    """
    intent = state.get("intent", "new_search")
    final_results = state.get("final_results", [])
    web_results = state.get("web_results", [])
    web_triggered = state.get("web_search_triggered", False)
    history = _format_history(state.get("messages", []))

    # ── Graceful degradation when Gemini API is down ──
    gemini_unavailable = time.time() < _rate_limited_until
    if gemini_unavailable and not web_triggered:
        if final_results:
            reply = (
                "My AI service is temporarily unavailable, but I found some visually similar products "
                "using image search. Results may not be perfectly curated — please try again in a moment!"
            )
        else:
            reply = (
                "My AI service is temporarily unavailable (high demand or quota limit). "
                "Please try again in a minute. If the problem persists, the daily quota may be exhausted."
            )
        products_to_show = final_results[:6] if final_results else []
        return {**state, "response": reply, "products_to_show": products_to_show}

    # Build context for Gemini
    if final_results:
        top = [r for r in final_results if (r.get("llm_score") or 0) >= 6][:6]
        product_summary = "\n".join(
            f"- {p.get('title', 'Unknown')} ({'₹' + str(int(p.get('price', 0))) if p.get('price') else 'price N/A'})"
            for p in (top or final_results[:3])
        )
        result_context = f"Found {len(top or final_results[:3])} relevant products:\n{product_summary}"
    elif web_triggered and web_results:
        result_context = f"No local results found. Searched online and found {len(web_results)} links."
    else:
        result_context = "No products found in the database or online."

    if not llm_service.is_enabled:
        # Simple fallback without Gemini
        if final_results:
            response = f"I found {len(final_results)} items for you!"
        elif web_triggered:
            response = "I couldn't find it locally, but here are some links to search online."
        elif intent == "general":
            response = "How can I help you find the perfect fashion item?"
        else:
            response = "I couldn't find matching products. Try describing the style or occasion."
        return {**state, "response": response, "products_to_show": final_results[:6]}

    tone_guide = {
        "new_search": "excited and helpful",
        "refine": "acknowledging the refinement and helpful",
        "feedback_positive": "warm and encouraging, maybe suggest variations",
        "feedback_negative": "apologetic and solution-focused",
        "general": "friendly and conversational",
    }

    prompt = (
        f"You are a friendly AI fashion shopping assistant. "
        f"Tone: {tone_guide.get(intent, 'helpful')}.\n\n"
        f"Conversation:\n{history}\n\n"
        f"What happened: {result_context}\n\n"
        "Write a short reply (2-3 sentences max). Rules:\n"
        "- Do NOT list the products — they are shown as cards separately\n"
        "- If web search was used: say you found some links to search online. "
        "  NEVER describe or predict what those links contain — you don't know. "
        "  Do NOT say 'I found shoe options' or 'I found kurta links' — just say "
        "  'I found some links you can explore' or similar\n"
        "- If no results at all, suggest the user rephrase or try different attributes\n"
        "- If positive feedback, maybe ask if they want variations\n"
        "Return ONLY the reply text."
    )

    reply = _gemini_call(prompt)
    if not reply:
        reply = (
            f"I found {len(final_results)} items for you!" if final_results
            else "Here are some online links where you can search for this item."
            if web_triggered else "I couldn't find a match. Try describing the style or occasion differently."
        )

    # ── Append feature suggestion when products are shown ──
    # Only suggest when there's something to show AND this was a search intent
    if (final_results or web_triggered) and intent in ("new_search", "refine", "marketplace_search"):
        current_prefs = FashionFeatures(**state.get("user_preferences", {}))
        suggestion = _build_feature_suggestion(current_prefs)
        if suggestion:
            reply = f"{reply}\n\n{suggestion}"

    # Products to show: top-scored local results (score >= 6), or all if no LLM
    products_to_show = [r for r in final_results if (r.get("llm_score") or 0) >= 6]
    if not products_to_show and final_results:
        products_to_show = final_results[:6]

    return {
        **state,
        "response": reply,
        "products_to_show": products_to_show[:6],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 9 — Update Memory
# ─────────────────────────────────────────────────────────────────────────────

def update_memory(state: ChatState) -> ChatState:
    """
    Maintains the rolling 10-turn window.
    Resets per-turn fields. Preserves: user_preferences, clarification_count.
    Resets clarification_count if this turn had good results.
    """
    messages = state.get("messages", [])
    MAX_MESSAGES = 20  # 10 user + 10 assistant = 20 messages

    # Add assistant reply to messages
    response = state.get("response", "")
    if response:
        messages = messages + [{"role": "assistant", "content": response}]

    # Trim to rolling 10-turn window
    if len(messages) > MAX_MESSAGES:
        messages = messages[-MAX_MESSAGES:]

    # Reset clarification count on successful search
    new_clarification_count = state.get("clarification_count", 0)
    if state.get("results_quality") == "good":
        new_clarification_count = 0

    return {
        **state,
        "messages": messages,
        "clarification_count": new_clarification_count,
        # Only reset heavyweight intermediate fields to free memory.
        # Do NOT clear output fields (web_results, intent, web_search_triggered,
        # products_to_show, response) — they are read by ChatService.invoke()
        # after the graph finishes. All per-turn fields are already reset via
        # initial_state at the start of each new invoke() call.
        "local_results": [],
        "final_results": [],
        "results_quality": "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Build LangGraph
# ─────────────────────────────────────────────────────────────────────────────

def _build_graph():
    graph = StateGraph(ChatState)

    # Add nodes
    graph.add_node("classify_intent",           classify_intent)
    graph.add_node("extract_fashion_features",  extract_fashion_features)
    graph.add_node("outfit_completion_node",    outfit_completion_node)
    graph.add_node("search_local_db",           search_local_db)
    graph.add_node("rerank_results",            rerank_results_node)
    graph.add_node("ask_clarification",         ask_clarification)
    graph.add_node("handle_feedback",           handle_feedback_node)
    graph.add_node("web_search",                web_search)
    graph.add_node("generate_response",         generate_response)
    graph.add_node("update_memory",             update_memory)

    # Entry point
    graph.add_edge(START, "classify_intent")

    # Intent routing — also routes to outfit_completion_node when bot is
    # waiting for the user to specify what TYPE of complement they want
    def _intent_router(s: ChatState) -> str:
        if s["intent"] == "outfit_completion" or s.get("awaiting_outfit_detail"):
            return "outfit_completion_node"
        if s["intent"] in ("new_search", "refine", "marketplace_search"):
            return "extract_fashion_features"
        if "feedback" in s["intent"]:
            return "handle_feedback"
        return "generate_response"

    graph.add_conditional_edges(
        "classify_intent",
        _intent_router,
        {
            "outfit_completion_node":   "outfit_completion_node",
            "extract_fashion_features": "extract_fashion_features",
            "handle_feedback":          "handle_feedback",
            "generate_response":        "generate_response",
        },
    )

    # Outfit completion always goes straight to update_memory:
    #   Turn 1 (clarification): response=question is already set, awaiting=True
    #   Turn 2 (ReAct done):    response=outfit_response is set by ReAct subgraph
    # In both cases generate_response is skipped — outfit node owns the full response.
    graph.add_edge("outfit_completion_node", "update_memory")

    # Feature extraction → conditional routing:
    # - marketplace_search  : skip local DB → go straight to web_search
    # - new_search + garment_type missing + first turn (count=0) → ask clarification FIRST
    # - everything else     : run local DB search
    def _post_extract_router(s: ChatState) -> str:
        if s["intent"] == "marketplace_search":
            return "web_search"
        if (
            s["intent"] == "new_search"
            and "garment_type" in s.get("missing_slots", [])
            and s.get("clarification_count", 0) == 0
        ):
            return "ask_clarification"
        return "search_local_db"

    graph.add_conditional_edges(
        "extract_fashion_features",
        _post_extract_router,
        {
            "web_search":       "web_search",
            "ask_clarification": "ask_clarification",
            "search_local_db":  "search_local_db",
        },
    )
    graph.add_edge("search_local_db", "rerank_results")

    # Quality routing after rerank
    graph.add_conditional_edges(
        "rerank_results",
        quality_router,
        {
            "generate_response": "generate_response",
            "clarification_check": "ask_clarification",   # renamed for simplicity
            "web_search": "web_search",
        },
    )

    # Clarification count check inline in ask_clarification node
    # (clarification_router logic is embedded: if count >= 2 after increment → web_search)
    # We handle this by adding a post-clarification edge check:
    graph.add_conditional_edges(
        "ask_clarification",
        lambda s: "update_memory",   # always go to memory (user waits for next msg)
        {"update_memory": "update_memory"},
    )

    # Feedback routing
    graph.add_conditional_edges(
        "handle_feedback",
        feedback_router,
        {
            "extract_fashion_features": "extract_fashion_features",
            "generate_response": "generate_response",
            "web_search": "web_search",
        },
    )

    # Web search → response
    graph.add_edge("web_search", "generate_response")

    # All paths end at update_memory → END
    graph.add_edge("generate_response", "update_memory")
    graph.add_edge("update_memory", END)

    return graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Chat Service Singleton
# ─────────────────────────────────────────────────────────────────────────────

class ChatService:
    """
    Wraps the LangGraph graph and exposes a simple invoke() method.
    Maintains session memory (user_preferences, clarification_count) per
    conversation_id in a lightweight in-memory dict.
    """

    def __init__(self):
        self._graph = None
        # Session memory: {conversation_id: {user_preferences, clarification_count}}
        self._sessions: Dict[str, dict] = {}

    def initialize(self) -> None:
        global _outfit_agent
        if not LANGGRAPH_AVAILABLE:
            logger.warning("LangGraph not installed — chat using simple fallback")
            return
        try:
            self._graph = _build_graph()
            logger.info("LangGraph chat graph compiled successfully")
            _outfit_agent = _build_outfit_subgraph()
            logger.info("ReAct outfit subgraph compiled successfully")
        except Exception as exc:
            logger.error(f"LangGraph build failed: {exc}")

    def invoke(
        self,
        messages: List[dict],
        conversation_id: str,
        input_type: str = "text",
        image_description: Optional[str] = None,
        user_preferences: Optional[dict] = None,
        clarification_count: int = 0,
    ) -> dict:
        """
        Run the conversation through the graph.
        Returns {response, products_to_show, web_results, user_preferences, clarification_count, search_performed, web_search_performed}
        """
        # Restore session memory (server-side takes priority over client-sent)
        session                = self._sessions.get(conversation_id, {})
        accumulated_prefs      = session.get("user_preferences") or user_preferences or {}
        accumulated_count      = session.get("clarification_count", clarification_count)
        accumulated_dislikes   = session.get("disliked_features", {})
        last_shown_context     = session.get("last_shown", "")
        last_shown_product     = session.get("last_shown_product", {})   # Full product dict for ReAct
        last_search_query      = session.get("last_search_query", "")
        awaiting_outfit_detail = session.get("awaiting_outfit_detail", False)

        initial_state: ChatState = {
            "messages":            messages,
            "conversation_id":     conversation_id,
            "input_type":          input_type,
            "raw_query":           _get_last_user_message(messages),
            "image_description":   image_description,
            "current_features":    {},
            "user_preferences":    accumulated_prefs,
            "search_params":       {},
            "local_results":       [],
            "final_results":       [],
            "results_quality":     "",
            "web_search_triggered": False,
            "search_queries":      [],
            "web_results":         [],
            "intent":              "",
            "feedback_action":     "",
            "target_marketplace":  "",
            "clarification_count": accumulated_count,
            "response":            "",
            "products_to_show":    [],
            # Robustness fields
            "disliked_features":      accumulated_dislikes,
            "missing_slots":          [],
            "outfit_context":         last_shown_context,
            "last_shown_product":     last_shown_product,
            "last_search_query":      last_search_query,
            "awaiting_outfit_detail": awaiting_outfit_detail,
        }

        if self._graph is not None:
            run_config = {
                "run_name": f"fashion-chat",
                "tags": [input_type],
                "metadata": {
                    "conversation_id": conversation_id,
                    "input_type": input_type,
                    "message_count": len(messages),
                },
            }
            result = self._graph.invoke(initial_state, config=run_config)
        else:
            # Simple fallback without LangGraph
            result = _simple_fallback(initial_state)

        # Persist session memory server-side
        session_update: dict = {
            "user_preferences":    result.get("user_preferences", {}),
            "clarification_count": result.get("clarification_count", 0),
            "disliked_features":   result.get("disliked_features", {}),
            # Store the actual search query used this turn so web_search next turn
            # uses the right category (e.g. sandals, not kurta after outfit completion)
            "last_search_query":      result.get("search_params", {}).get("query", "")
                                      or result.get("last_search_query", "")
                                      or session.get("last_search_query", ""),
            "awaiting_outfit_detail": result.get("awaiting_outfit_detail", False),
        }
        # Remember the last shown products for outfit completion context
        shown = result.get("products_to_show", [])
        if shown:
            # Store full first product dict for ReAct subgraph attribute extraction
            session_update["last_shown_product"] = shown[0]
            titles = [p.get("title", "") for p in shown[:2] if p.get("title")]
            session_update["last_shown"] = " and ".join(titles)
        else:
            # Preserve from previous turn so outfit completion still has a reference
            if "last_shown_product" in session:
                session_update["last_shown_product"] = session["last_shown_product"]
            if "last_shown" in session:
                session_update["last_shown"] = session["last_shown"]
        self._sessions[conversation_id] = session_update

        return {
            "response": result.get("response", "How can I help you?"),
            "products_to_show": result.get("products_to_show", []),
            "web_results": result.get("web_results", []),
            "user_preferences": result.get("user_preferences", {}),
            "clarification_count": result.get("clarification_count", 0),
            "search_performed": result.get("intent", "") in ("new_search", "refine"),
            "web_search_performed": result.get("web_search_triggered", False),
        }


def _simple_fallback(state: ChatState) -> ChatState:
    """Minimal fallback when LangGraph is unavailable."""
    state = classify_intent(state)
    intent = state.get("intent", "new_search")
    if intent == "outfit_completion" or state.get("awaiting_outfit_detail"):
        # outfit_completion_node now runs ReAct internally (or clarification question).
        # Response is already set — skip generate_response and go straight to update_memory.
        state = outfit_completion_node(state)
        state = update_memory(state)
        return state
    elif intent == "marketplace_search":
        # Extract features first (handles image + text context), then web search
        state = extract_fashion_features(state)
        state = web_search(state)
    elif intent in ("new_search", "refine"):
        state = extract_fashion_features(state)
        # Proactive slot gate — ask before searching if garment_type is unknown
        if (
            intent == "new_search"
            and "garment_type" in state.get("missing_slots", [])
            and state.get("clarification_count", 0) == 0
        ):
            state = ask_clarification(state)
        else:
            state = search_local_db(state)
            state = rerank_results_node(state)
    elif "feedback" in intent:
        state = handle_feedback_node(state)
        action = state.get("feedback_action", "")
        if action == "wants_refinement":
            state = extract_fashion_features(state)
            state = search_local_db(state)
            state = rerank_results_node(state)
        elif action in ("wants_different", "very_unsatisfied"):
            state = web_search(state)
    state = generate_response(state)
    state = update_memory(state)
    return state


# Singleton
chat_service = ChatService()
