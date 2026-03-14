"""
Pydantic schemas for the AI Fashion Assistant chat system.

FashionFeatures  — structured outfit attributes extracted by Gemini
SearchParams     — validated FAISS search parameters
WebSearchResult  — web fallback result (title + URL + snippet)
ChatMessage      — single conversation turn
ChatRequest      — full request payload (JSON + optional image bytes)
ChatResponse     — API response with message, products, web links
"""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


# ── Feature extraction schema ─────────────────────────────────────────────

class FashionFeatures(BaseModel):
    """
    Structured outfit attributes extracted from conversation by Gemini.
    Used to build CLIP queries and FAISS filter dicts.
    """
    garment_type: Optional[str] = None   # "kurta", "dress", "jeans", "saree"
    color: Optional[List[str]] = None    # ["blue", "navy"]
    pattern: Optional[str] = None        # "floral", "solid", "striped", "embroidered"
    style: Optional[str] = None          # "ethnic", "casual", "formal", "boho"
    fit: Optional[str] = None            # "slim", "regular", "relaxed", "oversized"
    fabric: Optional[str] = None         # "cotton", "silk", "denim", "linen"
    occasion: Optional[str] = None       # "wedding", "casual", "office", "beach"
    gender: Optional[str] = None         # "men", "women", "unisex"
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    brand: Optional[str] = None
    sleeve_type: Optional[str] = None    # "full", "half", "sleeveless", "puffed"
    neckline: Optional[str] = None       # "mandarin", "round", "v-neck", "sweetheart"

    def merge(self, other: "FashionFeatures") -> "FashionFeatures":
        """
        Merge another FashionFeatures into this one.
        New values overwrite existing; None values never overwrite.
        This ensures accumulated session preferences are never lost.
        """
        data = self.model_dump()
        for k, v in other.model_dump().items():
            if v is not None:
                data[k] = v
        return FashionFeatures(**data)

    def to_clip_query(self) -> str:
        """
        Build an optimal CLIP text query from structured features.
        Order matters — most discriminative attributes first.
        """
        parts: List[str] = []
        if self.gender:       parts.append(self.gender)
        if self.garment_type: parts.append(self.garment_type)
        if self.color:        parts.extend(self.color)
        if self.pattern:      parts.append(self.pattern)
        if self.style:        parts.append(self.style)
        if self.fit:          parts.append(self.fit)
        if self.fabric:       parts.append(self.fabric)
        if self.occasion:     parts.append(f"for {self.occasion}")
        if self.sleeve_type:  parts.append(f"{self.sleeve_type} sleeves")
        if self.neckline:     parts.append(f"{self.neckline} neck")
        return " ".join(parts) if parts else ""

    # E-commerce platforms that must never be used as brand filters
    _MARKETPLACES: set = {
        "flipkart", "amazon", "myntra", "ajio", "meesho",
        "nykaa", "snapdeal", "tata cliq", "tatacliq", "shopsy",
    }

    def to_filters(self) -> Dict[str, Any]:
        """Build FAISS filter dict from structured features.

        Only passes filters that map reliably to DB columns.
        - price: always reliable
        - brand: reliable when user explicitly mentions a clothing brand
          (e-commerce platforms are blocked — they are not clothing brands)
        - category / gender: NOT passed — CLIP semantic search handles these
          (DB category values often don't match extracted terms like 'kurta')
        """
        f: Dict[str, Any] = {}
        if self.brand and self.brand.lower() not in self._MARKETPLACES:
            f["brand"] = self.brand
        if self.max_price is not None: f["max_price"] = self.max_price
        if self.min_price is not None: f["min_price"] = self.min_price
        return f

    def is_empty(self) -> bool:
        return all(v is None for v in self.model_dump().values())


# ── Search parameters ──────────────────────────────────────────────────────

class SearchParams(BaseModel):
    query: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    k: int = Field(default=12, ge=1, le=50)


# ── Web search result ─────────────────────────────────────────────────────

class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = None       # delivery info / description snippet
    price: Optional[str] = None         # e.g. "₹1,499"
    source_site: Optional[str] = None   # e.g. "Myntra", "ajio.com"
    image_url: Optional[str] = None     # product thumbnail (Serper results only)
    rating: Optional[float] = None      # e.g. 4.5
    rating_count: Optional[int] = None  # e.g. 2340
    source: Optional[str] = None        # "google_lens" | None (None = web/serper search)


# ── Chat message ──────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    image_included: bool = False


# ── API request / response ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    conversation_id: Optional[str] = None
    # Accumulated across session — sent back by frontend on each turn
    user_preferences: Optional[Dict[str, Any]] = None
    clarification_count: int = 0


class ChatResponse(BaseModel):
    message: str
    products: List[dict] = []           # SearchResult dicts
    web_results: List[WebSearchResult] = []
    conversation_id: str
    search_performed: bool = False
    web_search_performed: bool = False
    # Returned to frontend so it can send back on next turn
    user_preferences: Dict[str, Any] = Field(default_factory=dict)
    clarification_count: int = 0
