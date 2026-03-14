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
    │                              └─ otherwise           → web_search
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
  START → oa_extract_attributes → oa_style_coordinate → oa_generate_query → oa_search_web
       → oa_evaluate_results → [_outfit_react_router]
            ├── good or max_iter (5) → oa_format_response → END
            └── poor/mismatch        → oa_generate_query  (loop)
  oa_style_coordinate runs ONCE — acts as a fashion stylist to set ideal_style,
  color_palette, avoid, and two pre-built queries consumed by oa_generate_query.
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
    image_bytes: Optional[bytes]       # Raw uploaded image — used for Google Lens visual search

    # Feature extraction (this turn + accumulated session)
    current_features: dict        # FashionFeatures serialized dict (this turn)
    user_preferences: dict        # Accumulated FashionFeatures across session

    # Search
    search_params: dict           # SearchParams serialized dict (query string for web search)

    # Web search
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
    last_search_query: str         # The actual search query used in the previous turn

    # Sticky web-search mode: once True, kept for the session
    web_search_mode: bool          # Set when user searches a marketplace; sticks for the session

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

    # Fashion stylist guidance (set by oa_style_coordinate, consumed by oa_generate_query + oa_evaluate_results)
    stylist_guidance: dict         # ideal_style, color_palette, avoid, search_query, search_query_alt

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


# ── Model tier constants ──────────────────────────────────────────────────────
# Fast   — structured tasks: intent, extraction, rerank, slot-fill, verification
#          gemini-2.0-flash: no thinking overhead → ~0.5-1 s per call
# Chat   — conversational quality: generate_response, web_search reply
#          gemini-2.5-flash: richer language, used only for final reply generation
# Pro    — quality-critical: fashion stylist (oa_style_coordinate)
_FAST_MODEL = "gemini-2.5-flash"   # thinking disabled via thinking_budget=0 → fast structured calls
_CHAT_MODEL = "gemini-2.5-flash"   # thinking enabled → richer conversational replies
_PRO_MODEL  = "gemini-2.5-pro"

# Circuit breaker: skip Gemini calls for 60 s after a 429 error
_rate_limited_until: float = 0.0


@traceable(name="gemini_call", run_type="llm", tags=["gemini", "chat"])
def _gemini_call(prompt: str, model: str = _FAST_MODEL, disable_thinking: bool = True) -> Optional[str]:
    """Make a Gemini API call. Returns text or None on failure.

    disable_thinking=True (default): passes thinking_budget=0 to gemini-2.5-flash,
    disabling chain-of-thought and reducing latency from ~8 s to ~1-2 s.
    Pass disable_thinking=False for the final conversational reply (generate_response).
    Implements a circuit breaker for 429/503 errors.
    """
    global _rate_limited_until
    if not llm_service.is_enabled:
        return None
    if time.time() < _rate_limited_until:
        logger.debug("Gemini rate-limit circuit breaker active — skipping call")
        return None
    try:
        kwargs: dict = {"model": model, "contents": prompt}
        if disable_thinking:
            try:
                from google.genai import types as _gt
                kwargs["config"] = _gt.GenerateContentConfig(
                    thinking_config=_gt.ThinkingConfig(thinking_budget=0)
                )
            except Exception:
                pass  # SDK version doesn't support thinking_config — fall through without it
        response = llm_service._client.models.generate_content(**kwargs)
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

# Serper.dev API key (set in ChatService.initialize from config)
_serper_api_key: str = ""


def _gemini_vision_call(contents: list) -> Optional[str]:
    """Make a multimodal Gemini Vision call (list of text strings + PIL Images).
    Shares the same circuit-breaker state as _gemini_call.
    """
    global _rate_limited_until
    if not llm_service.is_enabled:
        return None
    if time.time() < _rate_limited_until:
        logger.debug("Gemini circuit breaker active — skipping vision call")
        return None
    try:
        _kwargs: dict = {"model": _FAST_MODEL, "contents": contents}
        try:
            from google.genai import types as _gt
            _kwargs["config"] = _gt.GenerateContentConfig(
                thinking_config=_gt.ThinkingConfig(thinking_budget=0)
            )
        except Exception:
            pass
        response = llm_service._client.models.generate_content(**_kwargs)
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
            logger.warning(f"Gemini vision call failed: {exc}")
        return None


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
# ReAct Outfit Subgraph — 6 nodes + router + builder
# ─────────────────────────────────────────────────────────────────────────────

# ── Fashion coordination lookup tables (Option C — used as Gemini fallback) ──

# Which accent colours complement a garment's primary colour
_COLOUR_COMPLEMENTS: Dict[str, List[str]] = {
    "navy":    ["gold", "silver", "white", "beige", "champagne"],
    "blue":    ["gold", "silver", "white", "beige", "tan"],
    "ivory":   ["gold", "rose gold", "pearl", "nude", "champagne"],
    "white":   ["gold", "silver", "navy", "black", "pastel"],
    "black":   ["silver", "gold", "white", "red", "nude"],
    "maroon":  ["gold", "cream", "ivory", "champagne", "nude"],
    "red":     ["gold", "black", "white", "silver"],
    "green":   ["gold", "copper", "white", "nude", "cream"],
    "pink":    ["gold", "silver", "white", "nude", "rose gold"],
    "yellow":  ["white", "brown", "gold", "tan"],
    "orange":  ["white", "gold", "brown", "cream"],
    "purple":  ["gold", "silver", "white", "nude"],
    "beige":   ["brown", "gold", "white", "navy", "tan"],
    "cream":   ["gold", "brown", "navy", "maroon", "tan"],
    "brown":   ["cream", "beige", "gold", "white", "tan"],
    "grey":    ["silver", "white", "black", "navy", "blush"],
}

# What style of complement suits each garment style
_STYLE_ITEM_MAP: Dict[str, Dict[str, str]] = {
    "ethnic": {
        "footwear":    "kolhapuri sandals OR juttis OR ethnic heels",
        "accessories": "gold OR kundan OR stone-studded ethnic jewellery",
        "watch":       "ethnic gold watch OR stone-studded analog watch",
        "bag":         "potli bag OR embroidered clutch",
        "bottom":      "ethnic palazzo OR dhoti pants OR sharara",
        "jewellery":   "kundan OR meenakari OR temple gold jewellery",
    },
    "casual": {
        "footwear":    "sneakers OR casual loafers OR flat sandals",
        "accessories": "minimal everyday accessories",
        "watch":       "sport watch OR smartwatch OR casual analog watch",
        "bag":         "backpack OR canvas tote OR crossbody bag",
        "bottom":      "jeans OR casual trousers OR chinos",
    },
    "formal": {
        "footwear":    "oxford shoes OR pointed heels OR brogues OR derby shoes",
        "accessories": "minimal silver OR gold accessories",
        "watch":       "minimalist leather-strap analog watch",
        "bag":         "structured tote OR leather handbag",
        "bottom":      "formal trousers OR pencil skirt",
    },
    "western": {
        "footwear":    "ankle boots OR block heels OR ankle-strap heels",
        "accessories": "statement OR boho layered accessories",
        "watch":       "fashion watch OR bracelet watch",
        "bag":         "sling bag OR hobo bag OR mini clutch",
        "bottom":      "jeans OR mini skirt OR culottes",
    },
    "party": {
        "footwear":    "stilettos OR strappy heels OR embellished sandals",
        "accessories": "statement OR embellished chunky jewellery",
        "watch":       "embellished bracelet watch OR chain watch",
        "bag":         "evening clutch OR minaudière OR rhinestone bag",
        "bottom":      "mini skirt OR sequin trousers OR party shorts",
    },
    "boho": {
        "footwear":    "gladiator sandals OR suede ankle boots OR espadrilles",
        "accessories": "layered beaded OR tassel jewellery",
        "watch":       "leather-strap bohemian watch OR wooden watch",
        "bag":         "fringed bag OR wicker bag OR macrame bag",
        "bottom":      "flowy maxi skirt OR wide-leg pants",
    },
}


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


def oa_style_coordinate(state: OutfitState) -> OutfitState:
    """
    ReAct — Fashion Stylist step: runs ONCE before the first query.
    Asks Gemini "what would actually look good WITH this outfit?" —
    producing ideal_style, color_palette, and avoid guidance.
    This guidance is CONTEXT for oa_generate_query, NOT used verbatim as search queries
    (editorial fashion language doesn't match Google Shopping product titles).
    Falls back to _COLOUR_COMPLEMENTS + _STYLE_ITEM_MAP lookup tables when Gemini is down.
    """
    ref_product     = state.get("reference_product", {})
    ref_attrs       = state.get("reference_attributes", {})
    complement_item = state.get("complement_item", "") or state.get("complement_type", "accessories")
    user_gender     = state.get("user_gender", "")
    user_budget     = state.get("user_budget")

    ref_title  = ref_product.get("title", "an outfit")
    color      = ref_attrs.get("color", "")
    style      = ref_attrs.get("style", "")
    occasion   = ref_attrs.get("occasion", "")
    pattern    = ref_attrs.get("pattern", "")
    fabric     = ref_attrs.get("fabric", "")

    guidance: dict = {}

    if llm_service.is_enabled:
        gender_ctx = f"Shopper gender: {user_gender}" if user_gender else ""

        prompt = (
            "You are an expert Indian fashion stylist helping a shopper complete their outfit.\n\n"
            f"Reference outfit: {ref_title}\n"
            f"  - Primary colour: {color or 'unknown'}\n"
            f"  - Style: {style or 'unknown'}\n"
            f"  - Pattern: {pattern or 'none'}\n"
            f"  - Fabric: {fabric or 'unknown'}\n"
            f"  - Occasion: {occasion or 'everyday'}\n"
            f"{gender_ctx}\n"
            f"The shopper wants: {complement_item}\n\n"
            "Using colour theory and Indian fashion coordination rules, tell me:\n"
            f"1. What SPECIFIC STYLE of {complement_item} complements this outfit best?\n"
            f"   (e.g. 'minimalist gold analog watch', 'kolhapuri sandals', 'kundan earrings')\n"
            f"2. What COLOUR TONES work? (3-4 specific tones, e.g. 'gold, rose gold, champagne')\n"
            f"3. What should be AVOIDED? (styles/colours that clash)\n\n"
            "Return ONLY a JSON object (no markdown):\n"
            "{\n"
            '  "ideal_style": "specific style description",\n'
            '  "color_palette": "gold, rose gold, champagne",\n'
            '  "avoid": "dark brown leather, chunky sport styles"\n'
            "}"
        )
        raw = _gemini_call(prompt, model=_CHAT_MODEL, disable_thinking=False)   # Flash with thinking — good quality, faster than Pro
        if raw:
            try:
                guidance = json.loads(_clean_json(raw))
                logger.info(
                    f"Stylist guidance for '{complement_item}': "
                    f"ideal='{guidance.get('ideal_style','')}' "
                    f"colors='{guidance.get('color_palette','')}'"
                )
            except Exception as exc:
                logger.warning(f"Stylist guidance parse error: {exc}")

    # ── Rule-based fallback when Gemini is down / parse failed ─────────────
    if not guidance:
        comp_colours = _COLOUR_COMPLEMENTS.get(color.lower(), ["neutral", "gold", "white"]) if color else ["neutral"]
        style_key    = (style or "").lower()
        item_key     = complement_item.lower()
        style_desc   = (
            _STYLE_ITEM_MAP.get(style_key, {}).get(item_key)
            or _STYLE_ITEM_MAP.get(style_key, {}).get("accessories")
            or f"{style_key} {complement_item}"
        )
        palette      = ", ".join(comp_colours[:3])
        gender_pfx   = f"{user_gender} " if user_gender else ""
        budget_sfx   = f" under {int(user_budget)}" if user_budget else ""

        guidance = {
            "ideal_style":   style_desc or f"{style_key} {complement_item}",
            "color_palette": palette,
            "avoid":         "",
        }
        logger.info(f"Stylist guidance: rule-based fallback for '{complement_item}' | palette={palette}")

    return {**state, "stylist_guidance": guidance}


def oa_generate_query(state: OutfitState) -> OutfitState:
    """
    ReAct — Reason step: generate a SHORT, product-title-matching Google Shopping query.

    All iterations ask Gemini for a concise 3-5 word product search query using
    stylist guidance (ideal_style, color_palette) as context.
    Stylist editorial language ("minimalist gold analog watch ethnic wedding") is
    intentionally NOT used verbatim — Google Shopping matches on product titles,
    so shorter commercial terms like "women gold ethnic watch" perform much better.
    """
    complement_item  = state.get("complement_item", "") or state.get("complement_type", "accessories")
    refinement_hints = state.get("refinement_hints", [])
    iteration        = state.get("iteration", 0)
    user_gender      = state.get("user_gender", "")
    user_budget      = state.get("user_budget")
    guidance         = state.get("stylist_guidance", {})
    ref_attrs        = state.get("reference_attributes", {})

    ideal_style   = guidance.get("ideal_style", "")
    color_palette = guidance.get("color_palette", "")
    avoid         = guidance.get("avoid", "")
    style         = ref_attrs.get("style", "")
    occasion      = ref_attrs.get("occasion", "")

    query = ""

    if llm_service.is_enabled:
        hint_text = ""
        if refinement_hints:
            hint_text = (
                "\nPrevious queries that returned poor/mismatched results — do NOT repeat them:\n"
                + "\n".join(f"  - {h}" for h in refinement_hints[-3:])
                + "\nGenerate a clearly DIFFERENT query.\n"
            )

        # Vary strategy across iterations for better coverage
        angle_map = {
            0: f"Focus on item type + colour tone. Example format: '{user_gender} {color_palette.split(',')[0].strip() if color_palette else ''} {complement_item}'",
            1: f"Focus on style/occasion. Example format: '{user_gender} {style or ''} {complement_item} {occasion or ''}'",
            2: f"Focus on ideal style descriptor. Example format: '{user_gender} {ideal_style}'",
            3: f"Try a brand-agnostic product term that appears in Indian e-commerce titles.",
            4: f"Try the broadest possible query that still targets the correct item type.",
        }
        angle = angle_map.get(iteration, angle_map[4])

        budget_text = f" under ₹{int(user_budget)}" if user_budget else ""
        prompt = (
            f"Generate a Google Shopping search query to find: {complement_item}\n\n"
            f"Fashion context (use as inspiration, NOT verbatim):\n"
            f"  Ideal style: {ideal_style}\n"
            f"  Good colour tones: {color_palette}\n"
            f"  Avoid: {avoid or 'nothing specific'}\n"
            f"{hint_text}\n"
            f"Query angle for this iteration: {angle}\n\n"
            f"Rules:\n"
            f"  - Query MUST be about '{complement_item}' only — never about the garment\n"
            f"  - Keep it SHORT: 3-5 words maximum\n"
            f"  - Use simple commercial terms that appear in product TITLES on Myntra/Amazon\n"
            f"  - Do NOT use editorial language like 'minimalist' or long descriptive phrases\n"
            f"  - Start with gender if known: '{user_gender}'\n"
            f"  - Budget hint (add only if space allows): '{budget_text.strip()}'\n\n"
            "Return ONLY the query — one line, no quotes, no explanation."
        )
        raw = _gemini_call(prompt)
        if raw:
            query = raw.strip().strip('"').strip("'")

    # ── Fallback: rule-based short query ─────────────────────────────────────
    if not query:
        first_colour = color_palette.split(",")[0].strip() if color_palette else ""
        parts = [p for p in [user_gender, first_colour, style, complement_item] if p]
        query = " ".join(parts[:4])  # cap at 4 tokens

    logger.info(f"ReAct outfit iter {iteration + 1}/5: query='{query[:80]}'")
    return {**state, "current_query": query}


def oa_search_web(state: OutfitState) -> OutfitState:
    """
    ReAct — Act step: web search for the current_query.
    Tries Serper.dev Google Shopping first (real products with images/prices),
    then falls back to direct e-commerce search links.
    Grounding is intentionally NOT used — it reliably returns non-fashion sites.
    """
    query           = state.get("current_query", "")
    complement_item = state.get("complement_item", "") or state.get("complement_type", "accessories")

    if not query:
        return {**state, "web_results": []}

    # ── Serper.dev — direct search (no vision verification here) ─────────────
    # oa_evaluate_results handles quality/style checking — double verification
    # caused thumbnails to fail → empty results → apology loop.
    serper_results = _serper_search(query, num=6)
    if serper_results:
        logger.info(f"ReAct outfit Serper: {len(serper_results)} products for '{complement_item}' iter {state.get('iteration', 0) + 1}")
        return {**state, "web_results": serper_results}

    # ── Fallback: direct e-commerce search links ───────────────────────────────
    encoded = urllib.parse.quote_plus(query)
    short_q = query[:50]
    web_results = [
        {"title": f"Ajio — {short_q}",     "url": f"https://www.ajio.com/search/?text={encoded}",         "source_site": "ajio.com"},
        {"title": f"Myntra — {short_q}",   "url": f"https://www.myntra.com/search?rawQuery={encoded}",     "source_site": "myntra.com"},
        {"title": f"Amazon — {short_q}",   "url": f"https://www.amazon.in/s?k={encoded}",                  "source_site": "amazon.in"},
        {"title": f"Flipkart — {short_q}", "url": f"https://www.flipkart.com/search?q={encoded}",          "source_site": "flipkart.com"},
    ]
    logger.info(f"ReAct outfit: direct links fallback for '{query[:50]}'")
    return {**state, "web_results": web_results}


def oa_evaluate_results(state: OutfitState) -> OutfitState:
    """
    ReAct — Observation step: style-aware evaluation of search results.

    Checks two layers:
      1. Category match  — are these the right item type? (old logic)
      2. Style/colour match — do they fit the IDEAL STYLE and COLOUR PALETTE
                              from oa_style_coordinate? (new logic)

    This catches "brown sport watch returned for ivory silk wedding kurta" as
    'poor' even though it is technically a watch (correct category).
    """
    web_results      = state.get("web_results", [])
    query            = state.get("current_query", "")
    complement_type  = state.get("complement_type", "accessories")
    complement_item  = state.get("complement_item", "") or complement_type
    iteration        = state.get("iteration", 0)
    refinement_hints = list(state.get("refinement_hints", []))
    guidance         = state.get("stylist_guidance", {})
    ref_product      = state.get("reference_product", {})

    ideal_style   = guidance.get("ideal_style", complement_item)
    color_palette = guidance.get("color_palette", "")
    avoid         = guidance.get("avoid", "")
    ref_title     = ref_product.get("title", "the outfit")

    new_iteration = iteration + 1

    if not web_results:
        refinement_hints.append(f"Query '{query}' returned no results — try a different phrasing")
        return {
            **state,
            "iteration":         new_iteration,
            "evaluation":        "poor",
            "evaluation_reason": "No results returned",
            "refinement_hints":  refinement_hints,
        }

    # Direct search links (no title/snippet from Serper) — can't evaluate, accept
    all_direct = all(
        r.get("source_site") and not r.get("snippet") and not r.get("image_url")
        for r in web_results
    )
    if all_direct:
        logger.info(f"ReAct outfit iter {new_iteration}: direct links only — accepting as good")
        return {
            **state,
            "iteration":         new_iteration,
            "evaluation":        "good",
            "evaluation_reason": "Direct e-commerce search links provided",
            "refinement_hints":  refinement_hints,
        }

    # Style-aware Gemini evaluation
    if llm_service.is_enabled:
        results_text = "\n".join(
            f"- {r.get('title', 'Unknown')} | {r.get('price', '')} | {r.get('source_site', '')}"
            for r in web_results[:6]
        )
        prompt = (
            "You are a fashion stylist evaluating whether search results are suitable "
            "for an outfit completion recommendation.\n\n"
            f"Reference outfit: {ref_title}\n"
            f"Complement wanted: {complement_item}\n"
            f"Ideal style: {ideal_style}\n"
            f"Compatible colours: {color_palette}\n"
            f"Things to AVOID: {avoid or 'none specified'}\n\n"
            f"Search results returned:\n{results_text}\n\n"
            "Evaluate ALL results together:\n"
            f"  mismatch = wrong item type entirely (e.g. kurtas returned when '{complement_item}' was wanted)\n"
            f"  poor     = correct item type BUT wrong style or colour (e.g. dark sport watch for silk wedding kurta)\n"
            f"  good     = correct item type AND style/colour aligns with '{ideal_style}' and palette '{color_palette}'\n\n"
            "Respond with JSON only (no markdown):\n"
            '{"evaluation": "good|poor|mismatch", "reason": "one sentence explanation"}\n'
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
            # Record a specific, actionable hint for oa_generate_query
            hint = (
                f"Iter {new_iteration}: query='{query}' → {evaluation}. {reason}. "
                f"Need: {ideal_style} in {color_palette} tones. Avoid: {avoid}."
            )
            refinement_hints.append(hint)

        logger.info(f"ReAct outfit iter {new_iteration}: eval={evaluation} | {reason[:80]}")
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


def _generate_match_reasons(
    web_results: List[dict],
    ref_title: str,
    ref_color: str,
    ref_style: str,
    ref_occasion: str,
    complement_item: str,
    guidance: dict,
) -> List[dict]:
    """
    Single Gemini batch call that generates a 1-sentence styling reason for each product,
    explaining WHY it complements the reference outfit.
    Injects the reason into the 'snippet' field of each result dict.
    Returns the enriched list (original list unchanged on failure).
    """
    if not llm_service.is_enabled or not web_results:
        return web_results

    ideal_style   = guidance.get("ideal_style", "")
    color_palette = guidance.get("color_palette", "")

    numbered = "\n".join(
        f"{i + 1}. {r.get('title', 'Unknown')} {('— ' + r.get('price', '')) if r.get('price') else ''}"
        for i, r in enumerate(web_results)
    )

    prompt = (
        "You are an Indian fashion stylist. For each product below, write ONE short sentence "
        "(10–14 words max) explaining WHY it pairs well with the reference outfit.\n\n"
        f"Reference outfit: {ref_title}\n"
        f"  Colour: {ref_color or 'unknown'} | Style: {ref_style or 'unknown'} | Occasion: {ref_occasion or 'everyday'}\n"
        f"Ideal complement: {ideal_style}\n"
        f"Compatible colour tones: {color_palette}\n\n"
        f"Products:\n{numbered}\n\n"
        "Rules:\n"
        "  - Each reason must be specific to THAT product's title — not generic\n"
        "  - Mention colour or style coordination when possible\n"
        "  - Keep each reason under 14 words\n"
        "  - Do NOT start every sentence with 'This'\n\n"
        f"Return ONLY a JSON array of {len(web_results)} strings, one per product:\n"
        '["reason for product 1", "reason for product 2", ...]'
    )

    raw = _gemini_call(prompt)
    if not raw:
        return web_results

    try:
        reasons = json.loads(_clean_json(raw))
        if not isinstance(reasons, list):
            return web_results
        enriched = []
        for i, result in enumerate(web_results):
            r = dict(result)
            if i < len(reasons) and reasons[i]:
                r["snippet"] = str(reasons[i]).strip()
            enriched.append(r)
        logger.info(f"Match reasons generated for {len(enriched)} outfit products")
        return enriched
    except Exception as exc:
        logger.warning(f"Match reason parse error: {exc}")
        return web_results


def oa_format_response(state: OutfitState) -> OutfitState:
    """
    Generate the final outfit completion response text and per-product match reasons.
    Apologises gracefully if max iterations were reached without a perfect match.
    """
    web_results     = state.get("web_results", [])
    complement_type = state.get("complement_type", "accessories")
    complement_item = state.get("complement_item", "") or complement_type
    ref_product     = state.get("reference_product", {})
    ref_attrs       = state.get("reference_attributes", {})
    guidance        = state.get("stylist_guidance", {})
    iteration       = state.get("iteration", 0)
    evaluation      = state.get("evaluation", "good")

    ref_title   = ref_product.get("title", "your outfit")
    ref_color   = ref_attrs.get("color", "")
    ref_style   = ref_attrs.get("style", "")
    ref_occasion = ref_attrs.get("occasion", "")

    # ── Per-product match reasons (injected into snippet field) ──────────────
    web_results = _generate_match_reasons(
        web_results, ref_title, ref_color, ref_style, ref_occasion, complement_item, guidance
    )

    # ── Chat response text ───────────────────────────────────────────────────
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
                f"Found {len(web_results)} options. Write a short enthusiastic response (2 sentences).\n"
                f"Mention the specific item ('{complement_item}') and the style connection.\n"
                "Tell the user each card shows WHY the product complements their outfit.\n"
                "Return ONLY the reply text."
            )

        response_text = _gemini_call(prompt)
        if not response_text:
            response_text = (
                f"I found some {complement_item} options that should pair beautifully with your "
                f"{ref_style or ''} outfit! Each card explains why it works with your look."
            )
    else:
        response_text = (
            f"Here are some {complement_item} options to complement your look! "
            "Each card shows why it pairs well with your outfit."
        )

    logger.info(f"ReAct outfit complete | iterations={iteration} | eval={evaluation} | {len(web_results)} products")
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
    elif evaluation == "poor" and iteration >= 2:
        # Correct item type found — style not perfect but good enough after 2 refinements.
        # Better to show imperfect results than apologise repeatedly.
        logger.info(f"ReAct outfit: accepting 'poor' after {iteration} iters — showing best available")
        return "oa_format_response"
    elif iteration >= 5:
        logger.info(f"ReAct outfit: max 5 iterations reached — formatting best-effort response")
        return "oa_format_response"
    else:
        logger.info(f"ReAct outfit: iter {iteration} eval={evaluation} — refining query")
        return "oa_generate_query"


def _build_outfit_subgraph():
    """Compile the ReAct outfit completion subgraph (6 nodes)."""
    graph = StateGraph(OutfitState)

    graph.add_node("oa_extract_attributes", oa_extract_attributes)
    graph.add_node("oa_style_coordinate",   oa_style_coordinate)   # NEW — fashion stylist step
    graph.add_node("oa_generate_query",     oa_generate_query)
    graph.add_node("oa_search_web",         oa_search_web)
    graph.add_node("oa_evaluate_results",   oa_evaluate_results)
    graph.add_node("oa_format_response",    oa_format_response)

    # Linear first pass — stylist runs ONCE between attribute extraction and query generation
    graph.add_edge(START,                    "oa_extract_attributes")
    graph.add_edge("oa_extract_attributes",  "oa_style_coordinate")
    graph.add_edge("oa_style_coordinate",    "oa_generate_query")
    graph.add_edge("oa_generate_query",      "oa_search_web")
    graph.add_edge("oa_search_web",          "oa_evaluate_results")

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

    Also builds the search query string used by web_search.
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
                # Gemini sometimes returns lists for fields declared as str.
                # Coerce: join multi-value lists with "/" for string fields;
                # leave "color" alone (FashionFeatures.color is Optional[List[str]]).
                _str_fields = {"garment_type", "pattern", "style", "fit", "fabric",
                               "occasion", "gender", "brand", "sleeve_type", "neckline"}
                for field in _str_fields:
                    val = parsed.get(field)
                    if isinstance(val, list):
                        parsed[field] = "/".join(str(v) for v in val if v) or None
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

    # Build query string from merged features — used by web_search for the Serper/visual search
    # For image/hybrid inputs: use image_description as it is the product specification
    # For text inputs: build from structured features or fall back to raw message
    query = merged.to_clip_query()
    if not query:
        input_type = state.get("input_type", "text")
        if image_desc and input_type in ("image", "hybrid"):
            query = image_desc
        else:
            query = last_msg

    search_params = SearchParams(
        query=query,
        filters=merged.to_filters(),
        k=12,
    )

    # Feature 2 — Slot Filling: compute which critical attributes are still missing
    missing_slots = _compute_missing_slots(merged)

    logger.info(
        f"Features extracted | query='{query[:60]}' | "
        f"missing_slots={missing_slots}"
    )

    return {
        **state,
        "current_features": current_features.model_dump(),
        "user_preferences": merged.model_dump(),
        "search_params": search_params.model_dump(),
        "missing_slots": missing_slots,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 3 — Ask Clarification
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
        The subgraph searches ONLINE DIRECTLY via Serper web search.
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
        "stylist_guidance":     {},            # filled by oa_style_coordinate
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
        "intent":                "outfit_completion",
        "last_search_query":     outfit_result.get("current_query", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 7B — Web Search (Direct Links — no Grounding)
# ─────────────────────────────────────────────────────────────────────────────

def _serper_search(query: str, num: int = 8) -> List[dict]:
    """
    Call Serper.dev Google Shopping API for real product results with images and prices.
    Returns empty list if API key is not set or call fails — caller falls back to direct links.
    """
    if not _serper_api_key:
        return []
    try:
        import requests
        resp = requests.post(
            "https://google.serper.dev/shopping",
            headers={"X-API-KEY": _serper_api_key, "Content-Type": "application/json"},
            json={"q": query, "gl": "in", "hl": "en", "num": num},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("shopping", [])[:num]:
            results.append({
                "title":        item.get("title", ""),
                "url":          item.get("link", ""),
                "price":        item.get("price"),
                "image_url":    item.get("imageUrl"),
                "source_site":  item.get("source"),
                "rating":       item.get("rating"),
                "rating_count": item.get("ratingCount"),
                "snippet":      item.get("delivery"),
            })
        logger.info(f"Serper: {len(results)} products for '{query[:50]}'")
        return results
    except Exception as exc:
        logger.warning(f"Serper search failed: {exc}")
        return []


def _upload_image_for_lens(image_bytes: bytes) -> Optional[str]:
    """
    Upload image bytes to catbox.moe (free, no auth, permanent hosting).
    Returns a public URL suitable for Serper Lens, or None on failure.
    """
    try:
        import requests
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": ("image.jpg", image_bytes, "image/jpeg")},
            timeout=10,
        )
        resp.raise_for_status()
        url = resp.text.strip()
        if url.startswith("http"):
            return url
        return None
    except Exception as exc:
        logger.warning(f"Image upload for Lens failed: {exc}")
        return None


def _serper_lens_search(image_bytes: bytes, num: int = 6) -> List[dict]:
    """
    Call Serper.dev Google Lens API for exact visual matches.
    Uploads image to 0x0.st to get a public URL (Serper Lens requires a URL).
    Returns results in the same web_results dict format as _serper_search.
    """
    if not _serper_api_key or not image_bytes:
        return []
    try:
        import requests
        public_url = _upload_image_for_lens(image_bytes)
        if not public_url:
            logger.warning("Google Lens skipped — image upload failed")
            return []

        resp = requests.post(
            "https://google.serper.dev/lens",
            headers={"X-API-KEY": _serper_api_key, "Content-Type": "application/json"},
            json={"url": public_url},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        # Serper Lens returns matches under "organic" (not "visual_matches")
        items = data.get("organic") or data.get("visual_matches") or []
        for item in items[:num]:
            results.append({
                "title":       item.get("title", ""),
                "url":         item.get("link", ""),
                "price":       item.get("price"),
                "image_url":   item.get("imageUrl"),
                "source_site": item.get("source"),
                "snippet":     item.get("snippet", ""),
                "source":      "google_lens",
            })
        logger.info(f"Google Lens: {len(results)} visual matches for {public_url}")
        return results
    except Exception as exc:
        logger.warning(f"Google Lens search failed: {exc}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Serper ReAct Verification Agent
#
# Problem: Serper sometimes returns visually unrelated products (wrong category,
# wrong color, wrong style).  This ReAct agent adds a Gemini Vision verification
# step that checks each product image against the search context, rejects
# mismatches, and automatically refines the query for up to max_iter retries.
#
# ReAct loop per call:
#   Search → Observe (Vision verify) → Reason (enough good results?)
#          ↘ Refine query → Search … (repeat up to max_iter)
# ─────────────────────────────────────────────────────────────────────────────

def _sv_fetch_image_bytes(url: str) -> Optional[bytes]:
    """Fetch a product thumbnail with a short timeout. Returns None on failure."""
    try:
        import requests
        resp = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def _sv_verify_products(
    results: List[dict],
    context: str,
    query: str,
) -> tuple:
    """
    Gemini Vision batch verification of Serper product images.

    - Results without image_url: accepted via keyword overlap with query (fast path).
    - Results with image_url: thumbnails fetched in parallel, then ONE Gemini Vision
      call verifies all images against `context` in a single round-trip.

    Returns (verified: List[dict], rejection_hints: List[str]).
    Falls back to accepting ALL results if Gemini is unavailable or images fail to load.
    """
    import io
    hints: List[str] = []

    with_images    = [r for r in results if r.get("image_url")]
    without_images = [r for r in results if not r.get("image_url")]

    # Fast path: results with no image — accept by keyword overlap
    query_kws = set(query.lower().split())
    text_verified = [
        r for r in without_images
        if query_kws & set((r.get("title") or "").lower().split())
    ]

    if not with_images or not llm_service.is_enabled:
        return (text_verified + with_images), hints

    # Parallel thumbnail fetch (one thread per image, 4 s cap)
    image_bytes_list: List[Optional[bytes]] = [None] * len(with_images)

    def _fetch(idx: int, url: str):
        image_bytes_list[idx] = _sv_fetch_image_bytes(url)

    fetch_threads = [
        threading.Thread(target=_fetch, args=(i, r["image_url"]), daemon=True)
        for i, r in enumerate(with_images)
    ]
    for t in fetch_threads: t.start()
    for t in fetch_threads: t.join(timeout=4)

    try:
        import PIL.Image

        # Build list of (original_index, result, PIL_image) for all fetchable images
        fetched: List[tuple] = []
        for i, (r, img_bytes) in enumerate(zip(with_images, image_bytes_list)):
            if img_bytes:
                try:
                    fetched.append((i, r, PIL.Image.open(io.BytesIO(img_bytes))))
                except Exception:
                    pass

        # Images that couldn't be fetched/opened — accept them (can't verify)
        unfetchable_idx = {fp[0] for fp in fetched}
        unfetchable = [with_images[i] for i in range(len(with_images)) if i not in unfetchable_idx]

        if not fetched:
            return (text_verified + with_images), hints

        # Build multimodal Gemini contents: alternating text labels + PIL images
        contents: list = [
            f"Fashion product verifier.\n"
            f"Search context: \"{context}\"\n\n"
            f"Each image below is a product thumbnail. Decide for EACH:\n"
            f"  match=true  → correct item type AND visually fits the context\n"
            f"  match=false → wrong item type OR clearly does not match context\n\n"
        ]
        for pos, (orig_idx, r, img) in enumerate(fetched):
            contents.append(f"Image {pos}: {(r.get('title') or 'Unknown')[:60]}\n")
            contents.append(img)
        contents.append(
            f"\nReturn ONLY a JSON array — one object per image (no markdown):\n"
            f'[{{"index": 0, "match": true, "reason": "brief reason"}}, ...]'
        )

        raw = _gemini_vision_call(contents)
        if not raw:
            # Vision call failed — accept all (graceful degradation)
            return (text_verified + with_images), hints

        verdicts = json.loads(_clean_json(raw))
        if not isinstance(verdicts, list):
            raise ValueError("Expected JSON list")

        verdict_by_pos = {v.get("index"): v for v in verdicts}
        vision_verified: List[dict] = []
        for pos, (orig_idx, r, _) in enumerate(fetched):
            v = verdict_by_pos.get(pos, {})
            if v.get("match", True):   # default True if verdict missing
                vision_verified.append(r)
            else:
                hints.append(
                    f"'{(r.get('title') or '')[:50]}' rejected: {v.get('reason', 'does not match')}"
                )

        logger.info(
            f"Vision verify: {len(vision_verified)}/{len(fetched)} passed "
            f"| {len(unfetchable)} unverifiable accepted | {len(hints)} rejections"
        )
        return (text_verified + vision_verified + unfetchable), hints

    except Exception as exc:
        logger.warning(f"Vision verify error ({exc}) — accepting all results as fallback")
        return (text_verified + with_images), hints


def _sv_refine_query(original_query: str, context: str, hints: List[str]) -> str:
    """
    Ask Gemini to generate a better Serper query based on what was rejected.
    Falls back to the original query if Gemini is unavailable.
    """
    if not llm_service.is_enabled or not hints:
        return original_query

    hint_text = "\n".join(f"  - {h}" for h in hints[-4:])
    prompt = (
        f"A Google Shopping search returned mismatched products.\n\n"
        f"Original query: '{original_query}'\n"
        f"What I'm actually looking for: '{context}'\n\n"
        f"Products that FAILED visual verification:\n{hint_text}\n\n"
        "Generate ONE better Google Shopping search query (3-6 words).\n"
        "Rules:\n"
        "  - Be more specific about the exact item type\n"
        "  - Use commercial product-title terms (not editorial language)\n"
        "  - Address the mismatch reason from the failures above\n"
        "Return ONLY the query — one line, no quotes, no explanation."
    )
    raw = _gemini_call(prompt)
    if raw:
        refined = raw.strip().strip('"').strip("'")
        logger.info(f"Serper query refined: '{original_query}' → '{refined}'")
        return refined
    return original_query


def _serper_react_search(
    query: str,
    context: str,
    num: int = 8,
    max_iter: int = 3,
) -> List[dict]:
    """
    Serper Google Shopping search with Gemini Vision verification and ReAct retry.

    ReAct cycle (max `max_iter` iterations):
      1. Search  — call Serper with current query
      2. Observe — verify each product image with Gemini Vision
      3. Reason  — if < 3 verified results and iterations remain, refine query

    Returns verified results. Falls back to last iteration's raw results if
    verification consistently fails (e.g. Gemini Vision unavailable / all images
    unfetchable).
    """
    if not _serper_api_key:
        return []

    verified: List[dict] = []
    all_hints: List[str] = []
    current_query = query
    last_raw: List[dict] = []

    for iteration in range(max_iter):
        # ACT — search
        raw_results = _serper_search(current_query, num)
        if raw_results:
            last_raw = raw_results

        if not raw_results:
            all_hints.append(f"Query '{current_query}' returned no results")
            if iteration < max_iter - 1:
                current_query = _sv_refine_query(query, context, all_hints)
            continue

        # OBSERVE — verify images
        newly_verified, iter_hints = _sv_verify_products(raw_results, context, current_query)
        all_hints.extend(iter_hints)

        # Merge, deduplicate by URL
        seen_urls = {r.get("url") for r in verified}
        for r in newly_verified:
            if r.get("url") not in seen_urls:
                verified.append(r)
                seen_urls.add(r.get("url"))

        logger.info(
            f"Serper ReAct iter {iteration + 1}/{max_iter}: "
            f"query='{current_query[:60]}' → {len(newly_verified)}/{len(raw_results)} verified "
            f"| total={len(verified)}"
        )

        # REASON — enough good results?
        if len(verified) >= 3:
            break

        if iteration < max_iter - 1:
            current_query = _sv_refine_query(query, context, all_hints)

    if verified:
        return verified[:num]
    # Fallback: return raw results from last iteration (Gemini Vision unavailable)
    logger.info("Serper ReAct: no verified results — returning raw last-iteration results")
    return last_raw[:num]


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

    # ── Step 3: Try Serper.dev (with ReAct visual verification), fall back to direct links ──
    raw_q   = search_queries[0]
    encoded = urllib.parse.quote_plus(raw_q)
    short_q = raw_q[:55]

    input_type  = state.get("input_type", "text")
    image_bytes = state.get("image_bytes")
    image_desc  = state.get("image_description", "")

    # ── Parallel visual search threads (image inputs only) ───────────────
    visual_web_results: List[dict] = []
    lens_results:       List[dict] = []

    def _run_visual_web():
        nonlocal visual_web_results
        if input_type not in ("image", "hybrid"):
            return
        if not _serper_api_key or not image_desc:
            return
        # Use the condensed query as the search term; full image_description as
        # the verification context (gives Gemini Vision the richest matching signal).
        clip_query = (state.get("search_params") or {}).get("query", "")
        search_query = clip_query if clip_query else image_desc.split(".")[0][:100]
        results = _serper_react_search(search_query, context=image_desc, num=6)
        if results:
            logger.info(f"Visual web: {len(results)} verified products for image search")
            visual_web_results.extend(results)

    def _run_lens():
        nonlocal lens_results
        if input_type not in ("image", "hybrid") or not image_bytes:
            return
        lens_results.extend(_serper_lens_search(image_bytes, num=6))

    # ── Text search + visual threads run in parallel ─────────────────────
    serper_results: List[dict] = []

    def _run_text_serper():
        nonlocal serper_results
        results = _serper_react_search(raw_q, context=base_query, max_iter=2)
        serper_results.extend(results)

    t_text = threading.Thread(target=_run_text_serper,  daemon=True)
    t_vis  = threading.Thread(target=_run_visual_web,   daemon=True)
    t_lens = threading.Thread(target=_run_lens,         daemon=True)
    t_text.start(); t_vis.start(); t_lens.start()
    t_text.join(timeout=20)
    t_vis.join(timeout=15)
    t_lens.join(timeout=20)

    # ── Merge visual web + Lens + text Serper results (deduplicate by URL) ──
    seen_urls: set = set()
    web_results: List[dict] = []
    for r in visual_web_results + lens_results + serper_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            web_results.append(r)

    if web_results:
        logger.info(
            f"Serper results | query='{raw_q[:60]}' | text={len(serper_results)} "
            f"visual_web={len(visual_web_results)} lens={len(lens_results)} "
            f"merged={len(web_results)}"
        )
    else:
        # Fallback: direct e-commerce search links (no API key or Serper failed)
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
        "web_search_mode":      state.get("web_search_mode", False) or (state.get("intent") == "marketplace_search"),
        "search_queries":       search_queries,
        "web_results":          web_results,
        "products_to_show":     [],
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
    web_results = state.get("web_results", [])
    web_triggered = state.get("web_search_triggered", False)
    products_to_show = state.get("products_to_show", [])
    history = _format_history(state.get("messages", []))

    # ── Graceful degradation when Gemini API is down ──
    gemini_unavailable = time.time() < _rate_limited_until
    if gemini_unavailable and not web_triggered:
        reply = (
            "My AI service is temporarily unavailable (high demand or quota limit). "
            "Please try again in a minute. If the problem persists, the daily quota may be exhausted."
        )
        return {**state, "response": reply, "products_to_show": products_to_show}

    # Build context for Gemini
    if web_triggered and web_results:
        result_context = f"Searched online and found {len(web_results)} links/products."
    else:
        result_context = "No products found online."

    if not llm_service.is_enabled:
        # Simple fallback without Gemini
        if web_triggered:
            response = "Here are some links to search for this item online."
        elif intent == "general":
            response = "How can I help you find the perfect fashion item?"
        else:
            response = "I couldn't find matching products. Try describing the style or occasion."
        return {**state, "response": response, "products_to_show": products_to_show}

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

    reply = _gemini_call(prompt, model=_CHAT_MODEL, disable_thinking=False)  # thinking on for richer reply
    if not reply:
        reply = (
            "Here are some online links where you can search for this item."
            if web_triggered else "I couldn't find a match. Try describing the style or occasion differently."
        )

    # ── Append feature suggestion when products are shown ──
    # Only suggest when there's something to show AND this was a search intent
    if web_triggered and intent in ("new_search", "refine", "marketplace_search"):
        current_prefs = FashionFeatures(**state.get("user_preferences", {}))
        suggestion = _build_feature_suggestion(current_prefs)
        if suggestion:
            reply = f"{reply}\n\n{suggestion}"

    return {
        **state,
        "response": reply,
        "products_to_show": products_to_show,
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

    # Reset clarification count on successful web search
    new_clarification_count = state.get("clarification_count", 0)
    if state.get("web_search_triggered"):
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
    # - marketplace_search  : go straight to web_search
    # - new_search + garment_type missing + first turn (count=0) → ask clarification FIRST
    # - everything else     : web_search (local DB removed)
    def _post_extract_router(s: ChatState) -> str:
        if s["intent"] == "marketplace_search":
            return "web_search"
        if (
            s["intent"] == "new_search"
            and "garment_type" in s.get("missing_slots", [])
            and s.get("clarification_count", 0) == 0
            and s.get("input_type", "text") not in ("image", "hybrid")  # image speaks for itself
        ):
            return "ask_clarification"
        return "web_search"

    graph.add_conditional_edges(
        "extract_fashion_features",
        _post_extract_router,
        {
            "web_search":        "web_search",
            "ask_clarification": "ask_clarification",
        },
    )

    # After clarification the bot waits for the next user message — always → update_memory
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
        global _outfit_agent, _serper_api_key
        if not LANGGRAPH_AVAILABLE:
            logger.warning("LangGraph not installed — chat using simple fallback")
            return
        try:
            from app.config import get_settings
            settings = get_settings()
            _serper_api_key = settings.serper_api_key
            if _serper_api_key:
                logger.info("Serper.dev API key loaded — ReAct-verified product cards enabled")
            else:
                logger.info("Serper.dev API key not set — using direct links only")
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
        image_bytes: Optional[bytes] = None,
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
        web_search_mode        = session.get("web_search_mode", False)   # Sticky online-only mode

        initial_state: ChatState = {
            "messages":            messages,
            "conversation_id":     conversation_id,
            "input_type":          input_type,
            "raw_query":           _get_last_user_message(messages),
            "image_description":   image_description,
            "image_bytes":         image_bytes,
            "current_features":    {},
            "user_preferences":    accumulated_prefs,
            "search_params":       {},
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
            "web_search_mode":        web_search_mode,
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
            # Once True, stays True for the whole session thread
            "web_search_mode":        result.get("web_search_mode", False) or session.get("web_search_mode", False),
        }
        # Remember the last shown products for outfit completion context.
        # Check local products first, then Serper web results (both carry title/image).
        shown = result.get("products_to_show", [])
        web_res = result.get("web_results", [])
        if shown:
            session_update["last_shown_product"] = shown[0]
            titles = [p.get("title", "") for p in shown[:2] if p.get("title")]
            session_update["last_shown"] = " and ".join(titles)
        elif web_res and web_res[0].get("title"):
            # Web search result (Serper product card) — use as outfit reference too
            session_update["last_shown_product"] = web_res[0]
            titles = [r.get("title", "") for r in web_res[:2] if r.get("title")]
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
        # Skip for image/hybrid inputs: the uploaded image already defines the product
        if (
            intent == "new_search"
            and "garment_type" in state.get("missing_slots", [])
            and state.get("clarification_count", 0) == 0
            and state.get("input_type", "text") not in ("image", "hybrid")
        ):
            state = ask_clarification(state)
        else:
            state = web_search(state)
    elif "feedback" in intent:
        state = handle_feedback_node(state)
        action = state.get("feedback_action", "")
        if action == "wants_refinement":
            state = extract_fashion_features(state)
            state = web_search(state)
        elif action in ("wants_different", "very_unsatisfied"):
            state = web_search(state)
    state = generate_response(state)
    state = update_memory(state)
    return state


# Singleton
chat_service = ChatService()
