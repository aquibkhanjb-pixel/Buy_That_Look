"""Trend Analyzer endpoint — what's trending in Indian fashion right now."""

import json
import time
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.logging import logger
from app.services.llm_service import llm_service

router = APIRouter()

# ── Schemas ───────────────────────────────────────────────────────────────────

class TrendItem(BaseModel):
    name: str                    # e.g. "Pastel Co-ord Sets"
    description: str             # 1-2 sentence explanation
    category: str                # e.g. "Women", "Men", "Accessories"
    badge: str                   # "🔥 Hot", "📈 Rising", "✨ New"
    search_query: str            # pre-filled query for the chat assistant
    example_items: List[str]     # 2-3 specific product examples

class TrendsResponse(BaseModel):
    trends: List[TrendItem]
    updated_at: str
    source: str = "Serper News + Gemini AI"

# ── Simple in-memory cache (1 hour TTL) ─────────────────────────────────────

_cache: Optional[TrendsResponse] = None
_cache_ts: float = 0
_CACHE_TTL = 3600  # 1 hour


# ── Serper news fetch ─────────────────────────────────────────────────────────

def _fetch_fashion_news() -> List[dict]:
    """Fetch recent Indian fashion trend articles from Serper News."""
    import os, requests
    api_key = os.getenv("SERPER_API_KEY", "")
    if not api_key:
        return []
    try:
        resp = requests.post(
            "https://google.serper.dev/news",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": "fashion trends India 2026", "gl": "in", "hl": "en", "num": 10},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("news", [])
    except Exception as exc:
        logger.warning(f"Serper news fetch failed: {exc}")
        return []


# ── Gemini trend extraction ───────────────────────────────────────────────────

_TREND_PROMPT = """You are a fashion trend analyst for the Indian market.

Based on the following recent fashion news headlines and snippets, identify the 6 most prominent current fashion trends in India.

NEWS ARTICLES:
{news_text}

Return a JSON array of exactly 6 trend objects. Each object must have:
- "name": short catchy trend name (3-5 words), e.g. "Pastel Co-ord Sets"
- "description": 1-2 sentences explaining the trend and why it's popular
- "category": one of "Women", "Men", "Unisex", "Accessories"
- "badge": one of "🔥 Hot", "📈 Rising", "✨ New" — pick based on how mainstream it is
- "search_query": a natural language query a user would type to find this, e.g. "pastel co-ord set for women"
- "example_items": list of exactly 3 specific product examples (short names only)

Return ONLY the JSON array, no markdown, no explanation.
"""

def _extract_trends_with_gemini(news_articles: List[dict]) -> List[TrendItem]:
    """Use Gemini to parse news into structured trend objects."""
    if not llm_service.is_enabled or not news_articles:
        return _fallback_trends()

    news_text = "\n".join(
        f"- {a.get('title', '')} | {a.get('snippet', '')}"
        for a in news_articles[:10]
    )

    try:
        from google.genai import types as _gt
        prompt = _TREND_PROMPT.format(news_text=news_text)
        response = llm_service._client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=_gt.GenerateContentConfig(
                thinking_config=_gt.ThinkingConfig(thinking_budget=0)
            ),
        )
        raw = response.text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        return [TrendItem(**item) for item in data[:6]]
    except Exception as exc:
        logger.warning(f"Gemini trend extraction failed: {exc}")
        return _fallback_trends()


def _fallback_trends() -> List[TrendItem]:
    """Static fallback trends when API calls fail."""
    return [
        TrendItem(
            name="Pastel Co-ord Sets",
            description="Matching pastel-toned top and bottom sets dominating Indian ethnic and western wear. Perfect for brunches and casual outings.",
            category="Women", badge="🔥 Hot",
            search_query="pastel co-ord set for women",
            example_items=["Lavender co-ord set", "Mint green matching set", "Peach top and trouser set"],
        ),
        TrendItem(
            name="Oversized Linen Shirts",
            description="Breathable linen oversized shirts are the go-to for Indian summers, worn over trousers or as a beach cover-up.",
            category="Men", badge="📈 Rising",
            search_query="oversized linen shirt for men",
            example_items=["White linen shirt", "Beige oversized shirt", "Striped linen top"],
        ),
        TrendItem(
            name="Embroidered Kurtis",
            description="Intricate thread embroidery on kurtis is seeing a massive revival, blending traditional craftsmanship with modern silhouettes.",
            category="Women", badge="🔥 Hot",
            search_query="embroidered kurti for women",
            example_items=["Chikankari kurti", "Mirror work kurti", "Floral embroidered kurti"],
        ),
        TrendItem(
            name="Cargo Pants",
            description="Utility-style cargo pants with multiple pockets have crossed into mainstream Indian streetwear for both men and women.",
            category="Unisex", badge="✨ New",
            search_query="cargo pants streetwear",
            example_items=["Olive cargo pants", "Black cargo trousers", "Beige utility pants"],
        ),
        TrendItem(
            name="Statement Jhumkas",
            description="Bold oversized jhumka earrings are back, with oxidised silver and terracotta finishes leading the trend.",
            category="Accessories", badge="📈 Rising",
            search_query="statement jhumka earrings",
            example_items=["Oxidised jhumkas", "Terracotta earrings", "Gold chandbali earrings"],
        ),
        TrendItem(
            name="Relaxed Blazers",
            description="Unstructured, relaxed-fit blazers in earthy tones are replacing formal stiff suits for both office and casual wear.",
            category="Unisex", badge="✨ New",
            search_query="relaxed fit blazer unisex",
            example_items=["Camel relaxed blazer", "Olive unstructured blazer", "Cream linen blazer"],
        ),
    ]


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=TrendsResponse)
async def get_trends(refresh: bool = False):
    """
    Returns current Indian fashion trends.
    Results are cached for 1 hour. Pass ?refresh=true to force a fresh fetch.
    """
    global _cache, _cache_ts

    if not refresh and _cache and (time.time() - _cache_ts) < _CACHE_TTL:
        logger.info("Trends: serving from cache")
        return _cache

    logger.info("Trends: fetching fresh data")
    news = _fetch_fashion_news()
    trends = _extract_trends_with_gemini(news)

    from datetime import datetime, timezone
    response = TrendsResponse(
        trends=trends,
        updated_at=datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC"),
    )
    _cache = response
    _cache_ts = time.time()
    return response
