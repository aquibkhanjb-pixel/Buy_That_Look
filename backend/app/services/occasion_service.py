"""
Occasion Planner Service — AI-powered complete outfit builder.

Improvements:
  1. Swap generates 3 candidates, scores each via pairwise graph, returns best
  2. User hint text folds into swap search query; post-swap compatibility check
  3. Brand tier filter: budget / midrange / premium
  4. Pairwise compatibility graph — scores every outfit pair, flags clashes
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Dict, List, Optional, Tuple

import requests
from loguru import logger

from app.config import get_settings

settings = get_settings()

_JUDGE_MODEL    = "gemini-2.5-flash"
_EXTRACT_MODEL  = "gemini-2.5-flash"
_MAX_JUDGE_ITERS = 3
_SEARCH_TIMEOUT  = 12
_IMAGE_TIMEOUT   = 4
_N_SWAP_CANDIDATES = 3

# ── Rate limit ────────────────────────────────────────────────────────────────
_usage_store: Dict[str, int] = {}
FREE_DAILY_LIMIT = 2


def check_and_increment_usage(user_key: str, is_premium: bool) -> bool:
    if is_premium:
        return True
    key = f"{user_key}:{date.today()}"
    count = _usage_store.get(key, 0)
    if count >= FREE_DAILY_LIMIT:
        return False
    _usage_store[key] = count + 1
    return True


# ── Brand tier ────────────────────────────────────────────────────────────────
BRAND_TIERS = {
    "budget":   {"terms": ["affordable", "budget friendly", "cheap"], "price_factor": 0.55},
    "midrange": {"terms": [],                                          "price_factor": 1.00},
    "premium":  {"terms": ["premium", "designer", "luxury brand"],     "price_factor": 1.60},
}


# ── Category Definitions ──────────────────────────────────────────────────────
OCCASION_CATEGORIES: Dict[str, Dict[str, List[dict]]] = {
    "women": {
        "wedding": [
            {"id": "outfit",   "label": "Ethnic Outfit",       "sublabel": "Kurti Set / Saree / Lehenga",           "emoji": "👗", "budget_pct": 0.44, "default": True},
            {"id": "footwear", "label": "Footwear",            "sublabel": "Heels / Juttis / Embroidered Sandals",   "emoji": "👡", "budget_pct": 0.22, "default": True},
            {"id": "earrings", "label": "Earrings / Jewellery","sublabel": "Jhumkas / Chandbali / Necklace Set",     "emoji": "💍", "budget_pct": 0.15, "default": True},
            {"id": "clutch",   "label": "Clutch / Bag",        "sublabel": "Potli / Embroidered Clutch",             "emoji": "👜", "budget_pct": 0.10, "default": True},
            {"id": "dupatta",  "label": "Dupatta",             "sublabel": "Separate dupatta / stole",               "emoji": "🧣", "budget_pct": 0.05, "default": False},
            {"id": "bangles",  "label": "Bangles / Bracelet",  "sublabel": "Ethnic bangles / Kada",                  "emoji": "✨", "budget_pct": 0.04, "default": False},
        ],
        "party": [
            {"id": "outfit",   "label": "Party Outfit",        "sublabel": "Dress / Co-ord Set / Sequin Top+Pants", "emoji": "👗", "budget_pct": 0.50, "default": True},
            {"id": "footwear", "label": "Heels / Footwear",    "sublabel": "Block heels / Stilettos / Ankle boots", "emoji": "👠", "budget_pct": 0.25, "default": True},
            {"id": "earrings", "label": "Statement Earrings",  "sublabel": "Bold / drop / shoulder-duster earrings","emoji": "💫", "budget_pct": 0.12, "default": True},
            {"id": "clutch",   "label": "Clutch",              "sublabel": "Mini bag / party clutch / chain bag",   "emoji": "👛", "budget_pct": 0.13, "default": True},
        ],
        "office": [
            {"id": "outfit",   "label": "Office Outfit",       "sublabel": "Blazer Set / Formal Dress / Trousers",  "emoji": "💼", "budget_pct": 0.45, "default": True},
            {"id": "footwear", "label": "Formal Footwear",     "sublabel": "Block heels / Brogues / Loafers",       "emoji": "👟", "budget_pct": 0.30, "default": True},
            {"id": "bag",      "label": "Tote / Work Bag",     "sublabel": "Office tote / structured bag",          "emoji": "💼", "budget_pct": 0.15, "default": True},
            {"id": "earrings", "label": "Minimal Jewellery",   "sublabel": "Studs / simple necklace",               "emoji": "💎", "budget_pct": 0.10, "default": False},
        ],
        "date": [
            {"id": "outfit",   "label": "Date Outfit",         "sublabel": "Midi Dress / Crop+Skirt / Jumpsuit",    "emoji": "👗", "budget_pct": 0.48, "default": True},
            {"id": "footwear", "label": "Footwear",            "sublabel": "Block heels / Mules / Strappy sandals", "emoji": "👡", "budget_pct": 0.28, "default": True},
            {"id": "earrings", "label": "Earrings",            "sublabel": "Dainty hoops / pearl drops / studs",    "emoji": "✨", "budget_pct": 0.12, "default": True},
            {"id": "bag",      "label": "Bag",                 "sublabel": "Mini bag / sling / shoulder bag",       "emoji": "👜", "budget_pct": 0.12, "default": True},
        ],
        "casual": [
            {"id": "top",      "label": "Top",                 "sublabel": "T-shirt / Crop top / Casual kurti",     "emoji": "👕", "budget_pct": 0.30, "default": True},
            {"id": "bottom",   "label": "Bottom",              "sublabel": "Jeans / Palazzos / Skirt / Shorts",     "emoji": "👖", "budget_pct": 0.30, "default": True},
            {"id": "footwear", "label": "Footwear",            "sublabel": "Sneakers / Flats / Kolhapuri sandals",  "emoji": "👟", "budget_pct": 0.25, "default": True},
            {"id": "bag",      "label": "Bag / Tote",          "sublabel": "Canvas tote / sling / backpack",        "emoji": "🎒", "budget_pct": 0.15, "default": False},
        ],
    },
    "men": {
        "wedding": [
            {"id": "outfit",   "label": "Ethnic Outfit",       "sublabel": "Kurta Set / Sherwani / Indo-Western",   "emoji": "👘", "budget_pct": 0.52, "default": True},
            {"id": "footwear", "label": "Footwear",            "sublabel": "Mojari / Kolhapuri / Ethnic Loafers",   "emoji": "👞", "budget_pct": 0.26, "default": True},
            {"id": "dupatta",  "label": "Dupatta / Stole",     "sublabel": "Silk dupatta / brooch stole",           "emoji": "🧣", "budget_pct": 0.12, "default": True},
            {"id": "watch",    "label": "Watch",               "sublabel": "Formal / ethnic watch",                 "emoji": "⌚", "budget_pct": 0.10, "default": False},
        ],
        "party": [
            {"id": "outfit",   "label": "Party Outfit",        "sublabel": "Shirt + Trousers / Blazer Set",         "emoji": "👔", "budget_pct": 0.48, "default": True},
            {"id": "footwear", "label": "Footwear",            "sublabel": "Chelsea boots / Loafers / Derby shoes", "emoji": "👞", "budget_pct": 0.30, "default": True},
            {"id": "watch",    "label": "Watch",               "sublabel": "Smart / casual watch",                  "emoji": "⌚", "budget_pct": 0.12, "default": False},
            {"id": "belt",     "label": "Belt",                "sublabel": "Leather belt",                          "emoji": "🪢", "budget_pct": 0.10, "default": False},
        ],
        "office": [
            {"id": "outfit",   "label": "Office Outfit",       "sublabel": "Formal Shirt + Trousers / Suit",        "emoji": "👔", "budget_pct": 0.45, "default": True},
            {"id": "footwear", "label": "Formal Shoes",        "sublabel": "Oxford / Derby / Monk strap shoes",     "emoji": "👞", "budget_pct": 0.32, "default": True},
            {"id": "belt",     "label": "Belt",                "sublabel": "Genuine leather formal belt",           "emoji": "🪢", "budget_pct": 0.10, "default": False},
            {"id": "watch",    "label": "Watch",               "sublabel": "Formal / business watch",               "emoji": "⌚", "budget_pct": 0.08, "default": False},
            {"id": "tie",      "label": "Tie / Pocket Square", "sublabel": "Formal tie / silk pocket square",       "emoji": "🎽", "budget_pct": 0.05, "default": False},
        ],
        "casual": [
            {"id": "top",      "label": "Top",                 "sublabel": "T-shirt / Polo / Casual shirt",         "emoji": "👕", "budget_pct": 0.32, "default": True},
            {"id": "bottom",   "label": "Bottom",              "sublabel": "Jeans / Chinos / Shorts / Joggers",     "emoji": "👖", "budget_pct": 0.32, "default": True},
            {"id": "footwear", "label": "Footwear",            "sublabel": "Sneakers / Loafers / Casual shoes",     "emoji": "👟", "budget_pct": 0.26, "default": True},
            {"id": "cap",      "label": "Cap / Sunglasses",    "sublabel": "Baseball cap / sports sunglasses",      "emoji": "🕶️", "budget_pct": 0.10, "default": False},
        ],
    },
}

_OCCASION_TYPE_MAP = {
    "wedding": "wedding", "marriage": "wedding", "shaadi": "wedding",
    "mehendi": "wedding", "sangeet": "wedding",  "reception": "wedding",
    "engagement": "wedding", "festival": "wedding", "puja": "wedding",
    "diwali": "wedding", "eid": "wedding", "navratri": "wedding",
    "party": "party", "birthday": "party", "cocktail": "party",
    "club": "party", "dinner": "party", "nightout": "party",
    "farewell": "party", "anniversary": "party", "reunion": "party",
    "office": "office", "work": "office", "interview": "office",
    "meeting": "office", "corporate": "office",
    "date": "date", "romantic": "date",
    "casual": "casual", "outing": "casual", "trip": "casual",
    "brunch": "casual", "mall": "casual",
}

# Party sub-type → specific search style terms + vibe description
_PARTY_SUBTYPE_STYLES: Dict[str, Dict[str, str]] = {
    "birthday":    {"terms": "birthday party vibrant festive",    "vibe": "fun and vibrant birthday"},
    "farewell":    {"terms": "farewell party semi-formal elegant", "vibe": "smart-casual farewell send-off"},
    "anniversary": {"terms": "anniversary dinner romantic elegant","vibe": "romantic anniversary"},
    "friends":     {"terms": "friends gathering casual smart",     "vibe": "smart-casual get-together"},
    "cocktail":    {"terms": "cocktail party formal evening",      "vibe": "formal cocktail"},
    "reunion":     {"terms": "reunion gathering semi-formal",      "vibe": "semi-formal reunion"},
    "other":       {"terms": "party evening out",                  "vibe": "party"},
}


def _detect_occasion_type(text: str) -> str:
    t = text.lower()
    for kw, occ in _OCCASION_TYPE_MAP.items():
        if kw in t:
            return occ
    return "casual"


# ── Gemini helper ─────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, images_bytes: Optional[List[bytes]] = None,
                 model: str = _EXTRACT_MODEL) -> str:
    try:
        from app.services.llm_service import llm_service
        if not llm_service.is_enabled:
            return ""
        client = llm_service._client
        contents: list = []
        if images_bytes:
            try:
                import PIL.Image, io
                for b in images_bytes:
                    contents.append(PIL.Image.open(io.BytesIO(b)))
            except Exception as e:
                logger.warning(f"Image load failed: {e}")
        contents.append(prompt)
        resp = client.models.generate_content(model=model, contents=contents)
        return resp.text.strip()
    except Exception as exc:
        logger.warning(f"Gemini call failed: {exc}")
        return ""


def _parse_json(text: str) -> dict:
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {}


# ── Serper ────────────────────────────────────────────────────────────────────

def _serper_search(query: str, max_price: float, num: int = 8) -> List[dict]:
    api_key = settings.serper_api_key
    if not api_key:
        return []
    try:
        resp = requests.post(
            "https://google.serper.dev/shopping",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "gl": "in", "hl": "en", "num": num},
            timeout=_SEARCH_TIMEOUT,
        )
        resp.raise_for_status()
        results = []
        for item in resp.json().get("shopping", []):
            price_num = _parse_price(item.get("price", ""))
            if price_num > 0 and price_num > max_price * 1.25:
                continue
            results.append({
                "title":        item.get("title", ""),
                "url":          item.get("link", ""),
                "price":        item.get("price", ""),
                "price_num":    price_num,
                "image_url":    item.get("imageUrl", ""),
                "source_site":  item.get("source", ""),
                "rating":       item.get("rating"),
                "rating_count": item.get("ratingCount"),
            })
        return results
    except Exception as exc:
        logger.warning(f"Serper failed for '{query[:40]}': {exc}")
        return []


def _parse_price(s: str) -> float:
    if not s:
        return 0.0
    nums = re.findall(r'\d+', s.replace(",", ""))
    return float(nums[0]) if nums else 0.0


def _download_image(url: str) -> Optional[bytes]:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=_IMAGE_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
            return r.content
    except Exception:
        pass
    return None


# ── Context Extraction ────────────────────────────────────────────────────────

def extract_context(description: str) -> dict:
    prompt = f"""Extract structured information from this occasion description.
Description: "{description}"

Return ONLY a JSON object:
{{
  "occasion_type": "wedding|party|office|date|casual",
  "party_subtype": "birthday|farewell|anniversary|friends|cocktail|reunion|other",
  "gender": "women|men",
  "budget": <number in INR, default 3000>,
  "role": "guest|host|bride|groom|bridesmaid|attendee",
  "style": "ethnic|western|indo-western|formal|casual",
  "formality": "high|medium|casual",
  "special_notes": "<any extra requirements>"
}}
Rules:
- budget = extract number from "₹4000", "4k", "four thousand" etc. Default 3000.
- Style: infer from occasion if not stated (wedding→ethnic, office→formal, party→western).
- party_subtype: only fill if occasion_type is "party". Examples: farewell=farewell, birthday=birthday, anniversary=anniversary, "party with friends"=friends, cocktail=cocktail. Otherwise use "other".
- If occasion is NOT party, set party_subtype to "other"."""

    ctx = _parse_json(_call_gemini(prompt))

    if ctx.get("occasion_type") not in {"wedding", "party", "office", "date", "casual"}:
        ctx["occasion_type"] = _detect_occasion_type(description)
    if ctx.get("gender") not in {"women", "men"}:
        ctx["gender"] = "women"
    try:
        ctx["budget"] = float(ctx.get("budget", 3000))
    except (ValueError, TypeError):
        ctx["budget"] = 3000.0

    ctx.setdefault("role", "guest")
    ctx.setdefault("style", "ethnic" if ctx["occasion_type"] == "wedding" else "casual")
    ctx.setdefault("formality", "high" if ctx["occasion_type"] in {"wedding", "office"} else "medium")
    ctx.setdefault("special_notes", "")
    ctx.setdefault("party_subtype", "other")
    # Validate party_subtype
    valid_subtypes = {"birthday", "farewell", "anniversary", "friends", "cocktail", "reunion", "other"}
    if ctx.get("party_subtype") not in valid_subtypes:
        ctx["party_subtype"] = "other"
    ctx["original_description"] = description
    logger.info(f"Occasion context: {ctx}")
    return ctx


# ── Categories + Budget ───────────────────────────────────────────────────────

def get_categories(context: dict) -> List[dict]:
    gender = context.get("gender", "women")
    occasion = context.get("occasion_type", "casual")
    gender_cats = OCCASION_CATEGORIES.get(gender, OCCASION_CATEGORIES["women"])
    return gender_cats.get(occasion, gender_cats.get("casual", []))


def plan_budget(context: dict, selected_ids: List[str],
                custom_items: List[str], brand_tier: str = "midrange") -> Dict[str, float]:
    total = context.get("budget", 3000.0)
    tier_factor = BRAND_TIERS.get(brand_tier, BRAND_TIERS["midrange"])["price_factor"]
    effective_total = total * tier_factor

    all_cats = get_categories(context)
    cat_map = {c["id"]: c for c in all_cats}
    selected_cats = [cat_map[cid] for cid in selected_ids if cid in cat_map]
    total_pct = sum(c["budget_pct"] for c in selected_cats) or 1.0

    budgets: Dict[str, float] = {}
    std_budget = effective_total * (len(selected_ids) / max(len(selected_ids) + len(custom_items), 1))

    for cat in selected_cats:
        budgets[cat["id"]] = round(std_budget * cat["budget_pct"] / total_pct, 0)

    if custom_items:
        custom_share = effective_total * (len(custom_items) / max(len(selected_ids) + len(custom_items), 1))
        per_custom = round(custom_share / len(custom_items), 0)
        for item in custom_items:
            budgets[f"custom_{item.strip().lower().replace(' ', '_')}"] = per_custom

    return budgets


# ── Query Builder ─────────────────────────────────────────────────────────────

def _hint_to_search_query(hint: str, gender: str, occasion: str,
                          category_label: str, tier_terms: str) -> str:
    """Convert natural language user hint into a clean product shopping search query via Gemini."""
    prompt = f"""Convert this fashion preference into a concise product shopping search query (5-9 words).
Preference: "{hint}"
Context: {category_label} for {gender} attending a {occasion}

Rules:
- Output ONLY the search query, nothing else — no quotes, no explanation
- CRITICAL: If a brand name is mentioned (e.g. Nike, Zara, Mango, H&M, Levis, Adidas, Puma, Fabindia, W, Biba, Allen Solly, Louis Philippe, Van Heusen, Peter England, Raymond, Sabyasachi, etc.), you MUST include the EXACT brand name in the query
- Use specific product terms (color, material, style, fit)
- Remove filler like "I want", "something", "a bit more", "kind of", "please", "recommend me"
- Include gender and category if not obvious
- Examples:
  "Nike men white running sneakers" (brand preserved)
  "women royal blue velvet midi dress party"
  "Fabindia men kurta ethnic wedding"
  "Zara women black blazer party"
"""
    result = _call_gemini(prompt)
    if result:
        clean = result.strip().strip('"').strip("'").strip()
        if 2 <= len(clean.split()) <= 14:
            if tier_terms:
                clean += f" {tier_terms}"
            return clean

    # Fallback: basic stop-word cleanup
    stop_words = {"i", "want", "something", "a", "the", "please", "more", "bit",
                  "like", "prefer", "maybe", "kind", "of", "some", "get", "find"}
    words = [w for w in hint.lower().split() if w not in stop_words]
    base = f"{gender} {' '.join(words)} {category_label}"
    if tier_terms:
        base += f" {tier_terms}"
    return base.strip()


def _build_query(category_id: str, category_label: str, context: dict,
                 locked_pieces: Optional[List[dict]] = None,
                 custom_label: Optional[str] = None,
                 brand_tier: str = "midrange",
                 user_hint: str = "") -> str:
    gender       = context.get("gender", "women")
    occasion     = context.get("occasion_type", "wedding")
    style        = context.get("style", "ethnic")
    formality    = context.get("formality", "high")
    party_subtype = context.get("party_subtype", "other")
    tier_terms   = " ".join(BRAND_TIERS.get(brand_tier, {}).get("terms", []))

    # For party occasions, use subtype-specific terms for richer queries
    if occasion == "party":
        occasion_terms = _PARTY_SUBTYPE_STYLES.get(party_subtype, _PARTY_SUBTYPE_STYLES["other"])["terms"]
    else:
        occasion_terms = occasion

    # Color hints from locked pieces
    colors: List[str] = []
    if locked_pieces:
        for p in locked_pieces:
            for c in ["ivory","white","black","red","blue","green","gold","silver",
                      "pink","purple","beige","navy","maroon","cream","yellow",
                      "orange","brown","grey","gray","rust","teal","peach"]:
                if c in p.get("title", "").lower():
                    colors.append(c)
    color_hint = f"complement {' '.join(set(colors[:3]))}" if colors else ""

    # User hint → clean shopping query via Gemini (replaces raw text concatenation)
    if user_hint.strip():
        clean_query = _hint_to_search_query(user_hint, gender, occasion_terms, category_label, tier_terms)

        # Force-include any brand/proper noun the user mentioned that Gemini may have dropped.
        # Heuristic: capitalised words that aren't common English words.
        _COMMON_CAPS = {
            "I", "The", "A", "An", "And", "Or", "But", "In", "On", "At",
            "To", "For", "Of", "With", "My", "Me", "Can", "You", "Give",
            "Recommend", "Something", "More", "Please", "Find", "Want",
        }
        brand_candidates = [
            w.rstrip(".,!?") for w in user_hint.split()
            if len(w) > 1 and w[0].isupper() and w.rstrip(".,!?") not in _COMMON_CAPS
        ]
        for brand in brand_candidates:
            if brand.lower() not in clean_query.lower():
                clean_query = f"{brand} {clean_query}"
                logger.info(f"  Brand '{brand}' forced into swap query")
                break  # only one brand at a time

        return clean_query

    if custom_label:
        return f"{gender} {custom_label} {occasion_terms} {style} {color_hint} {tier_terms}".strip()

    templates = {
        "outfit":   f"{gender} {style} outfit {occasion_terms} {color_hint} {tier_terms}",
        "footwear": f"{gender} {occasion_terms} footwear {style} {color_hint} {tier_terms}",
        "earrings": f"women earrings jewellery {occasion_terms} {style} {color_hint} {tier_terms}",
        "clutch":   f"women clutch bag potli {occasion_terms} {style} {color_hint} {tier_terms}",
        "dupatta":  f"women dupatta stole {style} {color_hint} {tier_terms}",
        "bangles":  f"women bangles {occasion_terms} {style} {color_hint} {tier_terms}",
        "watch":    f"{gender} watch {formality} {color_hint} {tier_terms}",
        "belt":     f"men leather belt {formality} {color_hint} {tier_terms}",
        "tie":      f"men tie pocket square {formality} {color_hint} {tier_terms}",
        "cap":      f"men cap sunglasses casual {color_hint} {tier_terms}",
        "top":      f"{gender} top {style} casual {color_hint} {tier_terms}",
        "bottom":   f"{gender} bottom {style} casual {color_hint} {tier_terms}",
        "bag":      f"{gender} bag {occasion_terms} {style} {color_hint} {tier_terms}",
    }
    return templates.get(category_id,
        f"{gender} {category_label} {occasion_terms} {style} {color_hint} {tier_terms}").strip()


def _raw_to_piece(raw: dict, category_id: str, category_label: str, budget: float) -> dict:
    return {
        "category_id":    category_id,
        "category_label": category_label,
        "title":          raw["title"],
        "url":            raw["url"],
        "price":          raw["price"],
        "price_num":      raw["price_num"],
        "image_url":      raw.get("image_url", ""),
        "source_site":    raw.get("source_site", ""),
        "rating":         raw.get("rating"),
        "budget":         budget,
    }


# ── Pairwise Compatibility Graph ──────────────────────────────────────────────

def build_compatibility_graph(pieces: List[dict], context: dict,
                              use_images: bool = True) -> Dict[Tuple, dict]:
    """
    Judge every pair of pieces for compatibility.
    Returns { (cat_id_a, cat_id_b): {"score": 0|1|2, "reason": str} }
    Score: 2=compatible, 1=neutral, 0=incompatible
    use_images=False skips image downloads for speed (used in swap / judge loop).
    """
    if len(pieces) < 2:
        return {}

    pairs: List[Tuple[dict, dict]] = []
    for i in range(len(pieces)):
        for j in range(i + 1, len(pieces)):
            pairs.append((pieces[i], pieces[j]))

    pairs_text = "\n".join(
        f"{i+1}. [{a['category_label']}] {a['title'][:50]}"
        f" ↔ [{b['category_label']}] {b['title'][:50]}"
        for i, (a, b) in enumerate(pairs)
    )
    occasion      = context.get("occasion_type", "casual")
    gender        = context.get("gender", "women")
    party_subtype = context.get("party_subtype", "other")
    occasion_desc = (
        _PARTY_SUBTYPE_STYLES.get(party_subtype, {}).get("vibe", "party")
        if occasion == "party" else occasion
    )

    prompt = f"""You are an expert Indian fashion stylist. Judge compatibility of outfit pairs for: {occasion_desc} ({gender}).

Pairs:
{pairs_text}

Score each pair:
2 = Compatible (complement each other well)
1 = Neutral (no obvious clash, but not ideal)
0 = Incompatible (clash in colour, style, or formality)

Return ONLY JSON — no extra text:
{{
  "pairs": [
    {{"index": 1, "score": 2, "reason": ""}},
    {{"index": 2, "score": 0, "reason": "Casual sneakers clash with formal saree"}}
  ]
}}"""

    # Download images only when explicitly requested (initial outfit build)
    images: List[bytes] = []
    if use_images:
        for p in pieces[:4]:
            img = _download_image(p.get("image_url", ""))
            if img:
                images.append(img)

    raw = _call_gemini(prompt, images_bytes=images or None, model=_JUDGE_MODEL)
    result = _parse_json(raw)

    graph: Dict[Tuple, dict] = {}
    for i, (a, b) in enumerate(pairs):
        entry = next((p for p in result.get("pairs", []) if p.get("index") == i + 1), None)
        raw_score = entry.get("score", 1) if entry else 1
        try:
            score = int(raw_score) if not isinstance(raw_score, int) else raw_score
        except (ValueError, TypeError):
            score = 1
        reason = entry.get("reason", "") if entry else ""
        graph[(a["category_id"], b["category_id"])] = {"score": score, "reason": reason}
        graph[(b["category_id"], a["category_id"])] = {"score": score, "reason": reason}

    return graph


def _conflicts_from_graph(pieces: List[dict], graph: Dict[Tuple, dict]) -> Optional[dict]:
    """Extract score=0 conflict pairs from a pre-built graph. Returns None if all compatible."""
    conflicts = []
    seen: set = set()
    for (a_id, b_id), data in graph.items():
        key = tuple(sorted([a_id, b_id]))
        if key in seen or data["score"] > 0:
            continue
        seen.add(key)
        a = next((p for p in pieces if p["category_id"] == a_id), None)
        b = next((p for p in pieces if p["category_id"] == b_id), None)
        if a and b:
            conflicts.append({
                "piece_a_id":    a_id,
                "piece_b_id":    b_id,
                "piece_a_label": a["category_label"],
                "piece_b_label": b["category_label"],
                "reason":        data["reason"],
                "suggestion":    f"Try swapping your {b['category_label']} to better match the {a['category_label']}.",
            })
    if not conflicts:
        return None
    return {"has_conflicts": True, "conflicts": conflicts}


def check_compatibility(pieces: List[dict], context: dict) -> Optional[dict]:
    """
    Build pairwise graph (text-only) and return conflict info if any pair scores 0.
    Returns None if everything is compatible.
    """
    graph = build_compatibility_graph(pieces, context, use_images=False)
    return _conflicts_from_graph(pieces, graph)


# ── Candidate Scoring ─────────────────────────────────────────────────────────

def _best_of_candidates(candidates: List[dict], locked_pieces: List[dict],
                        context: dict) -> dict:
    """
    Score all candidates in a SINGLE text-only Gemini call (no image downloads).
    Returns the best-matching candidate.
    """
    if not locked_pieces or len(candidates) == 1:
        return candidates[0]

    occasion      = context.get("occasion_type", "casual")
    gender        = context.get("gender", "women")
    party_subtype = context.get("party_subtype", "other")
    occasion_desc = (
        _PARTY_SUBTYPE_STYLES.get(party_subtype, {}).get("vibe", "party")
        if occasion == "party" else occasion
    )

    locked_text = "\n".join(
        f"- [{p['category_label']}] {p['title'][:60]}"
        for p in locked_pieces
    )
    candidates_text = "\n".join(
        f"{i+1}. [{c['category_label']}] {c['title'][:60]} — ₹{c['price_num']}"
        for i, c in enumerate(candidates)
    )

    prompt = f"""You are an expert Indian fashion stylist. Score each candidate piece on how well it complements the already-selected pieces.

Occasion: {occasion_desc} | Gender: {gender}

Already selected:
{locked_text}

Candidates (pick the best one):
{candidates_text}

Rate each candidate 1–10 for style compatibility, colour harmony, and formality match with the selected pieces.
Return ONLY JSON with no extra text:
{{"scores": [<score_1>, <score_2>, ...]}}"""

    result = _parse_json(_call_gemini(prompt))
    raw_scores = result.get("scores", [])

    if raw_scores and len(raw_scores) >= len(candidates):
        try:
            # Gemini sometimes returns [{"score": 1}, ...] instead of [1, ...]
            numeric: List[float] = []
            for s in raw_scores[:len(candidates)]:
                if isinstance(s, (int, float)):
                    numeric.append(float(s))
                elif isinstance(s, dict):
                    # extract any numeric value from the dict
                    val = next((v for v in s.values() if isinstance(v, (int, float))), 0)
                    numeric.append(float(val))
                else:
                    numeric.append(0.0)

            best_idx = max(range(len(candidates)), key=lambda i: numeric[i])
            logger.info(f"  Batch candidate scores: {numeric}, best=#{best_idx+1} '{candidates[best_idx]['title'][:40]}'")
            return candidates[best_idx]
        except Exception as exc:
            logger.warning(f"  Candidate score comparison error: {exc} — returning rank-1")

    # Fallback: return first candidate (has image, usually best match from Serper ranking)
    logger.info("  Candidate scoring fallback → returning rank-1 result")
    return candidates[0]


# ── Single Category Search ────────────────────────────────────────────────────

def _search_one(category_id: str, category_label: str, budget: float,
                context: dict, locked_pieces: Optional[List[dict]] = None,
                custom_label: Optional[str] = None, brand_tier: str = "midrange",
                user_hint: str = "", n_candidates: int = 1) -> Optional[dict]:
    query = _build_query(category_id, category_label, context, locked_pieces,
                         custom_label, brand_tier, user_hint)
    logger.info(f"Search [{category_label}] — '{query[:70]}' — budget ₹{budget}")

    num = max(n_candidates + 3, 8)
    gender  = context.get("gender", "women")
    occasion = context.get("occasion_type", "casual")

    # ── Attempt 1: exact query, strict budget ──────────────────────────────────
    results = _serper_search(query, max_price=budget, num=num)

    # ── Attempt 2: simpler query, 2× budget ───────────────────────────────────
    if not results:
        if user_hint.strip():
            stop_words = {"i", "want", "something", "a", "the", "please", "more", "bit",
                          "like", "prefer", "maybe", "kind", "of", "some", "get", "find"}
            hint_words = [w for w in user_hint.lower().split() if w not in stop_words]
            simple = f"{gender} {' '.join(hint_words[:4])} {category_label}"
        else:
            simple = f"{gender} {category_label} {occasion}"
        logger.info(f"  Fallback-1 [{category_label}]: '{simple}' budget ₹{budget*2:.0f}")
        results = _serper_search(simple, max_price=budget * 2.0, num=6)

    # ── Attempt 3: most basic query, no price cap (ensure piece is never dropped)
    if not results:
        basic = f"{gender} {category_label}"
        logger.info(f"  Fallback-2 [{category_label}]: '{basic}' no price limit")
        results = _serper_search(basic, max_price=float("inf"), num=6)

    if not results:
        logger.warning(f"  No results at all for [{category_label}] — piece dropped")
        return None

    with_img = [r for r in results if r.get("image_url")]
    pool = (with_img + [r for r in results if not r.get("image_url")])[:max(n_candidates, 4)]

    candidates = [_raw_to_piece(r, category_id, category_label, budget) for r in pool]

    if n_candidates <= 1 or not locked_pieces:
        return candidates[0]

    return _best_of_candidates(candidates[:n_candidates], locked_pieces or [], context)


# ── ReAct Global Judge ────────────────────────────────────────────────────────

def _judge_outfit_global(pieces: List[dict], context: dict) -> dict:
    """Global judge: uses pairwise graph (text-only, no images) to find worst-scoring piece."""
    graph = build_compatibility_graph(pieces, context, use_images=False)

    # Compute per-piece average compatibility score
    piece_scores: Dict[str, float] = {}
    for p in pieces:
        related = [graph.get((p["category_id"], o["category_id"]), {}).get("score", 1)
                   for o in pieces if o["category_id"] != p["category_id"]]
        piece_scores[p["category_id"]] = sum(related) / len(related) if related else 2.0

    min_score = min(piece_scores.values()) if piece_scores else 2.0
    all_good = min_score >= 1.5   # only flag as 'needs_work' if clearly incompatible

    judge_pieces = []
    for p in pieces:
        s = piece_scores.get(p["category_id"], 2.0)
        score_label = "good" if s >= 1.5 else ("weak" if s >= 0.8 else "replace")
        reason = ""
        if score_label == "replace":
            conflicts = [
                graph.get((p["category_id"], o["category_id"]), {}).get("reason", "")
                for o in pieces
                if o["category_id"] != p["category_id"]
                and graph.get((p["category_id"], o["category_id"]), {}).get("score", 2) == 0
            ]
            reason = ". ".join(r for r in conflicts if r)
        judge_pieces.append({
            "category_id":   p["category_id"],
            "score":         score_label,
            "reason":        reason,
            "better_search": "",
        })

    return {"overall": "good" if all_good else "needs_work", "pieces": judge_pieces}


def react_judge_loop(pieces: List[dict], context: dict,
                     brand_tier: str = "midrange") -> List[dict]:
    if len(pieces) <= 1:
        return pieces

    current = list(pieces)

    for iteration in range(_MAX_JUDGE_ITERS):
        logger.info(f"ReAct iteration {iteration+1}/{_MAX_JUDGE_ITERS}")
        judgment = _judge_outfit_global(current, context)

        if judgment["overall"] == "good":
            logger.info("Judge accepted outfit ✓")
            break

        replaced = False
        for pj in judgment["pieces"]:
            if pj["score"] != "replace":
                continue
            cat_id = pj["category_id"]
            idx = next((i for i, p in enumerate(current) if p["category_id"] == cat_id), None)
            if idx is None:
                continue

            old = current[idx]
            locked = [p for i, p in enumerate(current) if i != idx]
            logger.info(f"Replacing [{old['category_label']}]: {pj.get('reason','')}")

            new_piece = _search_one(
                cat_id, old["category_label"], old["budget"],
                context, locked_pieces=locked,
                brand_tier=brand_tier, n_candidates=_N_SWAP_CANDIDATES,
            )
            if new_piece:
                current[idx] = new_piece
                replaced = True

        if not replaced:
            break

    return current


# ── Outfit Story ──────────────────────────────────────────────────────────────

def _generate_story(pieces: List[dict], context: dict) -> str:
    pieces_text = ", ".join(f"{p['category_label']} ({p['title'][:40]})" for p in pieces)
    occasion = context.get("occasion_type", "occasion")
    party_subtype = context.get("party_subtype", "other")

    # Build a richer occasion description for the stylist
    if occasion == "party" and party_subtype and party_subtype != "other":
        vibe = _PARTY_SUBTYPE_STYLES.get(party_subtype, {}).get("vibe", "party")
        occasion_desc = f"{vibe} ({context.get('role', 'guest')})"
    else:
        occasion_desc = f"{occasion} ({context.get('role', 'guest')})"

    prompt = f"""You are a friendly Indian fashion stylist. Write a short styling note (2-3 sentences) for:
Occasion: {occasion_desc} | Gender: {context.get('gender')} | Style: {context.get('style')}
Special notes: {context.get('special_notes') or 'none'}
Pieces: {pieces_text}

Explain why this outfit works for the specific occasion vibe, mention colour harmony, end with a styling tip. Conversational and warm. No markdown."""
    story = _call_gemini(prompt)
    return story or f"A curated {context.get('style','ethnic')} outfit perfect for {occasion_desc}."


# ── Budget Redistribution ─────────────────────────────────────────────────────

def _redistribute_budget(pieces: List[dict], context: dict,
                         brand_tier: str, original_budgets: Dict[str, float]) -> List[dict]:
    """
    If total spend is significantly below budget, redistribute the leftover to
    pieces that found cheap items and re-search them for better alternatives.
    """
    if not pieces:
        return pieces

    effective_budget = (
        context.get("budget", 3000)
        * BRAND_TIERS.get(brand_tier, BRAND_TIERS["midrange"])["price_factor"]
    )
    total_spent  = sum(p.get("price_num", 0) for p in pieces)
    leftover     = effective_budget - total_spent

    # Only redistribute if >20% of effective budget is unspent and >₹300 absolute
    if leftover < effective_budget * 0.20 or leftover < 300:
        return pieces

    # Find pieces that spent <50% of their allocated budget (got something cheap)
    upgradeable = [
        p for p in pieces
        if original_budgets.get(p["category_id"], 0) > 0
        and p.get("price_num", 0) < original_budgets.get(p["category_id"], 0) * 0.5
    ]

    if not upgradeable:
        return pieces

    bonus_each = leftover / len(upgradeable)
    logger.info(
        f"Budget redistribution: ₹{leftover:.0f} leftover → "
        f"bonus ₹{bonus_each:.0f} each for {len(upgradeable)} piece(s)"
    )

    upgraded = {p["category_id"]: p for p in pieces}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(
                _search_one,
                p["category_id"], p["category_label"],
                p["budget"] + bonus_each,
                context, None, None, brand_tier,
            ): p
            for p in upgradeable
        }
        for future in as_completed(futures):
            original = futures[future]
            try:
                new_piece = future.result()
            except Exception:
                continue
            if new_piece and new_piece.get("price_num", 0) > original.get("price_num", 0) * 1.1:
                upgraded[original["category_id"]] = new_piece
                logger.info(
                    f"  Upgraded [{original['category_label']}]: "
                    f"₹{original['price_num']:.0f} → ₹{new_piece['price_num']:.0f}"
                )

    return list(upgraded.values())


# ── Outfit Gap Detection ──────────────────────────────────────────────────────

def _detect_and_fill_gaps(pieces: List[dict], context: dict,
                           brand_tier: str, effective_budget: float) -> List[dict]:
    """
    Ask Gemini to look at the found pieces and identify truly essential missing items
    (e.g. shirt without trousers, kurta without pajama, saree without blouse).
    Searches for and appends any detected gaps as new outfit cards.
    Max 3 gaps, only when remaining budget allows.
    """
    if not pieces:
        return pieces

    occasion     = context.get("occasion_type", "casual")
    gender       = context.get("gender", "women")
    party_subtype = context.get("party_subtype", "other")
    occasion_desc = (
        _PARTY_SUBTYPE_STYLES.get(party_subtype, {}).get("vibe", "party")
        if occasion == "party" else occasion
    )

    total_spent   = sum(p.get("price_num", 0) for p in pieces)
    remaining     = effective_budget - total_spent
    existing_ids  = {p["category_id"] for p in pieces}

    pieces_text = "\n".join(
        f"- [{p['category_label']}] {p['title'][:70]}"
        for p in pieces
    )

    prompt = f"""You are an expert Indian fashion stylist. Analyse this partial outfit for a {occasion_desc} ({gender}).

Found so far:
{pieces_text}

Remaining budget: ₹{remaining:.0f}

Identify ONLY truly essential missing items needed to actually wear the outfit — items without which the person would be incomplete or underdressed.

Rules:
- Flag ONLY wearable essentials, NOT accessories (watch, belt, sunglasses are optional)
- Examples of essential gaps:
    * Shirt/kurta found but NO trousers/pants/pajama → gap: bottom wear
    * Saree found but NO blouse → gap: saree blouse
    * Blazer found but NO shirt/inner → gap: shirt/inner
    * Lehenga skirt found but NO blouse/choli → gap: lehenga blouse
    * Sherwani found but NO churidar/pant → gap: churidar / pant
- If the found piece is already a complete set (e.g. "kurta set", "co-ord set", "suit set", "shirt + trouser"), no gap needed
- Return empty gaps list if outfit is already complete or remaining budget < ₹200

Return ONLY JSON, no extra text:
{{
  "gaps": [
    {{
      "category_id": "bottom",
      "category_label": "Trousers / Pants",
      "budget_fraction": 0.40,
      "reason": "Shirt found but no trousers/pants"
    }}
  ]
}}"""

    result = _parse_json(_call_gemini(prompt))
    gaps   = result.get("gaps", [])

    if not gaps:
        logger.info("Gap check: outfit is complete, no essential items missing")
        return pieces

    new_pieces = list(pieces)
    remaining_after = remaining

    for gap in gaps[:3]:
        cat_id    = gap.get("category_id", "").strip()
        cat_label = gap.get("category_label", "").strip()
        frac      = float(gap.get("budget_fraction", 0.35))
        reason    = gap.get("reason", "")

        if not cat_id or not cat_label:
            continue
        if cat_id in {p["category_id"] for p in new_pieces}:
            continue  # already present
        if remaining_after < 200:
            logger.info(f"Gap [{cat_label}] skipped — remaining budget too low (₹{remaining_after:.0f})")
            continue

        gap_budget = min(remaining_after * frac, remaining_after * 0.6)
        gap_budget = max(gap_budget, 200.0)

        logger.info(f"Gap detected: [{cat_label}] — {reason} — searching with ₹{gap_budget:.0f}")

        new_piece = _search_one(
            cat_id, cat_label, gap_budget, context,
            locked_pieces=new_pieces,
            brand_tier=brand_tier,
            n_candidates=2,
        )

        if new_piece:
            new_pieces.append(new_piece)
            remaining_after -= new_piece.get("price_num", 0)
            logger.info(f"Gap filled: [{cat_label}] — '{new_piece['title'][:50]}'")
        else:
            logger.warning(f"Gap [{cat_label}] — search returned nothing")

    return new_pieces


# ── Main Build ────────────────────────────────────────────────────────────────

def build_outfit(context: dict, selected_ids: List[str],
                 custom_items: List[str], brand_tier: str = "midrange") -> dict:
    budgets = plan_budget(context, selected_ids, custom_items, brand_tier)
    all_cats = get_categories(context)
    cat_map = {c["id"]: c for c in all_cats}

    tasks = []
    for cid in selected_ids:
        if cid in cat_map:
            tasks.append((cid, cat_map[cid]["label"], budgets.get(cid, 500), False, None))
    for item in custom_items:
        key = f"custom_{item.strip().lower().replace(' ', '_')}"
        tasks.append((key, item.strip().title(), budgets.get(key, 400), True, item.strip()))

    pieces: List[dict] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(
                _search_one, cid, label, budget, context, None,
                custom_label if is_custom else None, brand_tier,
            ): (cid, label)
            for cid, label, budget, is_custom, custom_label in tasks
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                pieces.append(result)

    order = {cid: i for i, (cid, *_) in enumerate(tasks)}
    pieces.sort(key=lambda p: order.get(p["category_id"], 999))

    if not pieces:
        return {
            "pieces": [], "total_price": 0, "budget": context.get("budget", 3000),
            "outfit_story": "No results found. Try a different budget or occasion.",
            "compatibility_graph": [], "conflicts": None,
        }

    effective_budget = (
        context.get("budget", 3000)
        * BRAND_TIERS.get(brand_tier, BRAND_TIERS["midrange"])["price_factor"]
    )

    # ── Gap detection: add missing essential pieces (e.g. shirt without trousers)
    pieces = _detect_and_fill_gaps(pieces, context, brand_tier, effective_budget)
    pieces.sort(key=lambda p: order.get(p["category_id"], 999))

    # ── Budget redistribution: re-search cheap pieces with leftover budget ─────
    pieces = _redistribute_budget(pieces, context, brand_tier, budgets)
    pieces.sort(key=lambda p: order.get(p["category_id"], 999))

    pieces = react_judge_loop(pieces, context, brand_tier)
    graph  = build_compatibility_graph(pieces, context)
    story  = _generate_story(pieces, context)
    total  = sum(p.get("price_num", 0) for p in pieces)

    return {
        "pieces":              pieces,
        "total_price":         round(total, 2),
        "budget":              context.get("budget", 3000),
        "outfit_story":        story,
        "compatibility_graph": _serialize_graph(pieces, graph),
        "conflicts":           None,
    }


def _serialize_graph(pieces: List[dict], graph: Dict[Tuple, dict]) -> List[dict]:
    """Convert graph dict to list for JSON serialisation."""
    result = []
    seen: set = set()
    for p in pieces:
        for q in pieces:
            if p["category_id"] == q["category_id"]:
                continue
            key = tuple(sorted([p["category_id"], q["category_id"]]))
            if key in seen:
                continue
            seen.add(key)
            data = graph.get((p["category_id"], q["category_id"]), {"score": 1, "reason": ""})
            result.append({
                "a": p["category_id"], "a_label": p["category_label"],
                "b": q["category_id"], "b_label": q["category_label"],
                "score": data["score"], "reason": data["reason"],
            })
    return result


# ── Swap Piece (improved) ─────────────────────────────────────────────────────

def swap_piece(category_id: str, category_label: str, budget: float,
               context: dict, locked_pieces: List[dict],
               custom_label: Optional[str] = None,
               brand_tier: str = "midrange",
               user_hint: str = "") -> dict:
    """
    1. Generate _N_SWAP_CANDIDATES candidates (incorporating user_hint / brand in query)
    2. Score each via single batch Gemini call against locked pieces
    3. Return best candidate
    4. Build pairwise compatibility graph on full post-swap outfit (text-only, fast)
    5. Return piece + conflicts + updated compatibility_graph for frontend
    """
    logger.info(f"Swap [{category_label}] hint='{user_hint}' tier={brand_tier}")

    new_piece = _search_one(
        category_id, category_label, budget, context,
        locked_pieces=locked_pieces,
        custom_label=custom_label,
        brand_tier=brand_tier,
        user_hint=user_hint,
        n_candidates=_N_SWAP_CANDIDATES,
    )

    if not new_piece:
        return {"piece": None, "conflicts": None, "compatibility_graph": []}

    # Build graph once on full post-swap outfit — extract conflicts AND serialise for UI
    full_outfit = locked_pieces + [new_piece]
    graph = build_compatibility_graph(full_outfit, context, use_images=False)
    conflicts   = _conflicts_from_graph(full_outfit, graph)
    graph_list  = _serialize_graph(full_outfit, graph)

    return {"piece": new_piece, "conflicts": conflicts, "compatibility_graph": graph_list}
