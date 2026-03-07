"""
AI Fashion Assistant — Production LangGraph Chat Service (v2)

Graph architecture (13 nodes):

  START
    ↓
  classify_intent          ← Gemini: new_search / refine / feedback_* / general
    ↓ (conditional)
    ├── [new_search|refine]  → extract_fashion_features
    │                             ↓
    │                          search_local_db
    │                             ↓
    │                          rerank_results
    │                             ↓ (quality_router)
    │                          ┌─ good       → generate_response
    │                          ├─ mediocre   → clarification_check
    │                          │                  ↓ (clarification_router)
    │                          │              ┌── ask < 2x   → ask_clarification
    │                          │              └── 2x already → web_search
    │                          └─ poor/empty → web_search
    │
    ├── [feedback_*]         → handle_feedback
    │                             ↓ (feedback_router)
    │                          ┌── wants_refinement → extract_fashion_features
    │                          ├── wants_different  → extract_fashion_features
    │                          ├── just_positive    → generate_response
    │                          └── very_unsatisfied → web_search
    │
    └── [general]            → generate_response

  web_search                ← generates queries → Gemini grounding or direct links
    ↓
  generate_response
    ↓
  update_memory             ← trims messages to 10 turns, persists prefs
    ↓
  END

Memory strategy:
  user_preferences and clarification_count are stored in the ChatService instance
  per conversation_id (session memory, cleared on server restart).
  The frontend also mirrors them and sends back on each request as a safety net.
"""

import json
import re
import time
import urllib.parse
from typing import List, Optional, TypedDict, Dict, Any

from loguru import logger

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
    intent: str                   # "new_search"|"refine"|"feedback_positive"|"feedback_negative"|"general"
    feedback_action: str          # "text_response"|"wants_refinement"|"wants_different"|"very_unsatisfied"

    # Clarification tracking (persisted across turns)
    clarification_count: int

    # Response
    response: str
    products_to_show: List[dict]


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
        else:
            logger.warning(f"Gemini call failed: {exc}")
        return None


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
    if not llm_service.is_enabled:
        return {**state, "intent": "new_search"}

    history = _format_history(state.get("messages", []))
    last_msg = _get_last_user_message(state.get("messages", []))

    prompt = (
        "You are an AI fashion shopping assistant. Classify the user's latest message intent.\n\n"
        f"Conversation history:\n{history}\n\n"
        "Classify the intent into ONE of these categories:\n"
        "- new_search: user wants to find new/different products\n"
        "- refine: user wants to modify previous results (e.g. 'in red', 'under 500')\n"
        "- feedback_positive: user liked/approved the results ('love it', 'great', 'nice')\n"
        "- feedback_negative: user disliked results ('don't like', 'not what I wanted', 'show something else')\n"
        "- general: greeting, question about the bot, 'what did you do', 'thanks', etc.\n\n"
        "Return ONLY the category name, nothing else."
    )

    result = _gemini_call(prompt)
    valid = {"new_search", "refine", "feedback_positive", "feedback_negative", "general"}
    intent = result.strip().lower() if result else "new_search"
    if intent not in valid:
        intent = "new_search"

    logger.info(f"Intent classified: {intent}")
    return {**state, "intent": intent}


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
            '  "brand": "brand name or null",\n'
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

    # Merge with accumulated session preferences
    accumulated_features = FashionFeatures(**accumulated) if accumulated else FashionFeatures()
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

    logger.info(
        f"Features extracted | query='{clip_query[:60]}' | "
        f"filters={search_params.filters}"
    )

    return {
        **state,
        "current_features": current_features.model_dump(),
        "user_preferences": merged.model_dump(),
        "search_params": search_params.model_dump(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 3 — Search Local DB
# ─────────────────────────────────────────────────────────────────────────────

def search_local_db(state: ChatState) -> ChatState:
    """Search CLIP/FAISS with the extracted query and filters."""
    params_dict = state.get("search_params", {})
    params = SearchParams(**params_dict) if params_dict else SearchParams(query="")

    if not params.query or not search_engine.is_ready():
        logger.warning("Search engine not ready or empty query")
        return {**state, "local_results": []}

    raw_results = search_engine.search_by_text(
        query=params.query,
        k=params.k,
        filters=params.filters if params.filters else None,
    )

    logger.info(f"Local DB search: {len(raw_results)} candidates")
    return {**state, "local_results": raw_results}


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
    features = FashionFeatures(**state.get("current_features", {}))
    feature_context = features.to_clip_query()
    if feature_context:
        rerank_query = f"{rerank_query} ({feature_context})"

    final = llm_service.rerank_results(rerank_query, local_results)

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
    Gemini generates ONE focused clarifying question based on what information
    is missing from the user's request. Increments clarification_count.
    """
    features = FashionFeatures(**state.get("user_preferences", {}))
    history = _format_history(state.get("messages", []))
    count = state.get("clarification_count", 0)

    if llm_service.is_enabled:
        # Identify the most impactful missing field
        missing = []
        if not features.gender:       missing.append("gender (men/women)")
        if not features.garment_type: missing.append("garment type (dress/kurta/jeans etc)")
        if not features.occasion:     missing.append("occasion (casual/wedding/office etc)")
        if not features.max_price:    missing.append("budget/price range")

        missing_hint = f"Missing info: {', '.join(missing[:2])}" if missing else ""

        prompt = (
            "You are a helpful fashion assistant. "
            "The search didn't find great matches. Ask ONE short, specific question "
            "to help narrow the search.\n\n"
            f"Conversation so far:\n{history}\n\n"
            f"{missing_hint}\n\n"
            "Ask only ONE question. Keep it friendly and conversational. "
            "Do not list options — ask open-endedly. Return ONLY the question."
        )

        question = _gemini_call(prompt)
        if not question:
            question = "Could you tell me more about the occasion or style you have in mind?"
    else:
        question = "Could you tell me more about the style or occasion you're looking for?"

    new_count = count + 1
    logger.info(f"Clarification question #{new_count}: {question[:60]}")

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
        "Categories:\n"
        "- wants_refinement: change one thing (e.g. 'in red', 'cheaper', 'different style')\n"
        "- wants_different: completely different products, fresh search\n"
        "- just_positive: user is happy, no action needed ('love it', 'great', 'nice')\n"
        "- very_unsatisfied: frustrated, nothing worked ('hate these', 'completely wrong', 'useless')\n\n"
        "Return ONLY the category name."
    )

    result = _gemini_call(prompt)
    valid = {"wants_refinement", "wants_different", "just_positive", "very_unsatisfied"}
    action = result.strip().lower() if result else "wants_refinement"
    if action not in valid:
        action = "wants_refinement"

    logger.info(f"Feedback classified: {action}")
    return {**state, "feedback_action": action}


# ─────────────────────────────────────────────────────────────────────────────
# Conditional Edge — Feedback Router
# ─────────────────────────────────────────────────────────────────────────────

def feedback_router(state: ChatState) -> str:
    action = state.get("feedback_action", "wants_refinement")
    if action in ("wants_refinement", "wants_different"):
        return "extract_fashion_features"
    elif action == "just_positive":
        return "generate_response"
    else:  # very_unsatisfied
        return "web_search"


# ─────────────────────────────────────────────────────────────────────────────
# Node 7 — Web Search (Gemini Grounding + Direct Links Fallback)
# ─────────────────────────────────────────────────────────────────────────────

def web_search(state: ChatState) -> ChatState:
    """
    Attempts Gemini Grounding (google_search tool) for live product results.
    Falls back to generating direct e-commerce search URLs if grounding fails
    or if the free-tier model doesn't support it.
    """
    features = FashionFeatures(**state.get("user_preferences", {}))
    base_query = features.to_clip_query() or _get_last_user_message(state.get("messages", []))

    web_results: List[dict] = []

    # ── Step 1: Generate targeted search queries via Gemini ──
    if llm_service.is_enabled:
        prompt = (
            f"Generate 3 targeted search queries to find this fashion product on Indian e-commerce sites.\n"
            f"Product description: {base_query}\n\n"
            "Return a JSON array of 3 query strings, e.g.:\n"
            '["blue cotton kurta men", "mens ethnic blue kurta", "light blue regular fit kurta men"]'
        )
        raw = _gemini_call(prompt)
        search_queries: List[str] = []
        if raw:
            try:
                queries = json.loads(_clean_json(raw))
                search_queries = [str(q) for q in queries[:3] if q]
            except Exception:
                search_queries = [base_query]
        else:
            search_queries = [base_query]
    else:
        search_queries = [base_query]

    logger.info(f"Web search queries: {search_queries}")

    # ── Step 2: Try Gemini Grounding ──
    grounding_worked = False
    if llm_service.is_enabled and search_queries:
        try:
            from google.genai import types as genai_types

            grounding_prompt = (
                f"Find fashion products available to buy in India that match: {search_queries[0]}\n"
                "List 4-5 products with name, price and where to buy."
            )
            response = llm_service._client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=grounding_prompt,
                config=genai_types.GenerateContentConfig(
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
                ),
            )

            # Extract grounding chunks (URLs) if available
            grounding_chunks = []
            try:
                meta = response.candidates[0].grounding_metadata
                if meta and meta.grounding_chunks:
                    for chunk in meta.grounding_chunks:
                        if chunk.web:
                            grounding_chunks.append({
                                "title": chunk.web.title or "Product",
                                "url": chunk.web.uri,
                                "snippet": None,
                                "source_site": chunk.web.uri.split("/")[2] if chunk.web.uri else None,
                            })
            except Exception:
                pass

            if grounding_chunks:
                web_results = grounding_chunks[:5]
                grounding_worked = True
                logger.info(f"Gemini grounding returned {len(web_results)} results")
            elif response.text:
                # Grounding worked but no chunks — use text as snippet
                web_results = [{
                    "title": "Search Results",
                    "url": "",
                    "snippet": response.text[:300],
                    "source_site": "web",
                }]
                grounding_worked = True

        except Exception as exc:
            logger.warning(f"Gemini grounding failed: {exc} — using direct links")

    # ── Step 3: Fallback — generate direct e-commerce search links ──
    if not grounding_worked:
        encoded = urllib.parse.quote(search_queries[0] if search_queries else base_query)
        direct_links = [
            WebSearchResult(
                title=f"Search on Ajio: {search_queries[0][:40]}",
                url=f"https://www.ajio.com/s/{encoded}",
                source_site="ajio.com",
            ),
            WebSearchResult(
                title=f"Search on Myntra: {search_queries[0][:40]}",
                url=f"https://www.myntra.com/{encoded}",
                source_site="myntra.com",
            ),
            WebSearchResult(
                title=f"Search on Amazon: {search_queries[0][:40]}",
                url=f"https://www.amazon.in/s?k={encoded}",
                source_site="amazon.in",
            ),
            WebSearchResult(
                title=f"Search on Flipkart: {search_queries[0][:40]}",
                url=f"https://www.flipkart.com/search?q={encoded}",
                source_site="flipkart.com",
            ),
        ]
        web_results = [r.model_dump() for r in direct_links]
        logger.info("Using direct e-commerce search links as fallback")

    return {
        **state,
        "web_search_triggered": True,
        "search_queries": search_queries,
        "web_results": web_results,
        "final_results": [],   # No local products when web search is used
    }


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
        "- If web search was used, mention you found some links to explore online\n"
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
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("extract_fashion_features", extract_fashion_features)
    graph.add_node("search_local_db", search_local_db)
    graph.add_node("rerank_results", rerank_results_node)
    graph.add_node("ask_clarification", ask_clarification)
    graph.add_node("handle_feedback", handle_feedback_node)
    graph.add_node("web_search", web_search)
    graph.add_node("generate_response", generate_response)
    graph.add_node("update_memory", update_memory)

    # Entry point
    graph.add_edge(START, "classify_intent")

    # Intent routing
    graph.add_conditional_edges(
        "classify_intent",
        lambda s: (
            "extract_fashion_features" if s["intent"] in ("new_search", "refine")
            else "handle_feedback" if "feedback" in s["intent"]
            else "generate_response"
        ),
        {
            "extract_fashion_features": "extract_fashion_features",
            "handle_feedback": "handle_feedback",
            "generate_response": "generate_response",
        },
    )

    # Feature extraction → search pipeline
    graph.add_edge("extract_fashion_features", "search_local_db")
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
        if not LANGGRAPH_AVAILABLE:
            logger.warning("LangGraph not installed — chat using simple fallback")
            return
        try:
            self._graph = _build_graph()
            logger.info("LangGraph chat graph compiled successfully")
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
        session = self._sessions.get(conversation_id, {})
        accumulated_prefs = session.get("user_preferences") or user_preferences or {}
        accumulated_count = session.get("clarification_count", clarification_count)

        initial_state: ChatState = {
            "messages": messages,
            "conversation_id": conversation_id,
            "input_type": input_type,
            "raw_query": _get_last_user_message(messages),
            "image_description": image_description,
            "current_features": {},
            "user_preferences": accumulated_prefs,
            "search_params": {},
            "local_results": [],
            "final_results": [],
            "results_quality": "",
            "web_search_triggered": False,
            "search_queries": [],
            "web_results": [],
            "intent": "",
            "feedback_action": "",
            "clarification_count": accumulated_count,
            "response": "",
            "products_to_show": [],
        }

        if self._graph is not None:
            result = self._graph.invoke(initial_state)
        else:
            # Simple fallback without LangGraph
            result = _simple_fallback(initial_state)

        # Persist session memory server-side
        self._sessions[conversation_id] = {
            "user_preferences": result.get("user_preferences", {}),
            "clarification_count": result.get("clarification_count", 0),
        }

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
    if intent in ("new_search", "refine"):
        state = extract_fashion_features(state)
        state = search_local_db(state)
        state = rerank_results_node(state)
    elif "feedback" in intent:
        state = handle_feedback_node(state)
        action = state.get("feedback_action", "")
        if action in ("wants_refinement", "wants_different"):
            state = extract_fashion_features(state)
            state = search_local_db(state)
            state = rerank_results_node(state)
    state = generate_response(state)
    state = update_memory(state)
    return state


# Singleton
chat_service = ChatService()
