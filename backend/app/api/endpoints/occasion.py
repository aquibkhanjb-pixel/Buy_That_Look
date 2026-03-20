"""Occasion Planner API endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.core.logging import logger
from app.services.occasion_service import (
    extract_context,
    get_categories,
    build_outfit,
    swap_piece,
    check_and_increment_usage,
)

router = APIRouter()
_optional_bearer = HTTPBearer(auto_error=False)


def _get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> Optional[dict]:
    if not credentials:
        return None
    try:
        from app.core.auth import _decode
        return _decode(credentials.credentials)
    except Exception:
        return None


# ── Schemas ───────────────────────────────────────────────────────────────────

class CategoriesRequest(BaseModel):
    description: str


class PlanRequest(BaseModel):
    context: dict
    selected_ids: List[str]
    custom_items: List[str] = []
    brand_tier: str = "midrange"   # budget | midrange | premium


class SwapRequest(BaseModel):
    context: dict
    category_id: str
    category_label: str
    budget: float
    locked_pieces: List[dict] = []
    custom_label: Optional[str] = None
    brand_tier: str = "midrange"
    user_hint: str = ""            # optional modification text from user


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/categories")
def get_occasion_categories(
    body: CategoriesRequest,
    current_user: Optional[dict] = Depends(_get_optional_user),
):
    """Step 1 — Extract occasion context + return category MCQ."""
    if not body.description.strip():
        raise HTTPException(status_code=422, detail="Description cannot be empty")
    ctx  = extract_context(body.description.strip())
    cats = get_categories(ctx)
    return {"context": ctx, "categories": cats}


@router.post("/plan")
def plan_occasion(
    body: PlanRequest,
    current_user: Optional[dict] = Depends(_get_optional_user),
):
    """Step 2 — Build outfit. Free: 2/day. Premium: unlimited."""
    is_premium = current_user and current_user.get("tier") == "premium"
    user_id    = current_user["sub"] if current_user else None

    if not check_and_increment_usage(user_id, is_premium):
        raise HTTPException(
            status_code=403,
            detail="Free tier allows 2 outfit plans per day. Upgrade to Premium for unlimited.",
        )
    if not body.selected_ids and not body.custom_items:
        raise HTTPException(status_code=422, detail="Select at least one category")

    logger.info(
        f"Occasion plan — {body.context.get('occasion_type')} / "
        f"{body.context.get('gender')} / ₹{body.context.get('budget')} / "
        f"tier={body.brand_tier}"
    )
    return build_outfit(
        context=body.context,
        selected_ids=body.selected_ids,
        custom_items=body.custom_items,
        brand_tier=body.brand_tier,
    )


@router.post("/swap")
def swap_outfit_piece(
    body: SwapRequest,
    current_user: Optional[dict] = Depends(_get_optional_user),
):
    """
    Swap one piece.
    - Generates 3 candidates, scores via pairwise graph, returns best.
    - Runs post-swap compatibility check on full outfit.
    - Does NOT count against daily limit.
    """
    result = swap_piece(
        category_id=body.category_id,
        category_label=body.category_label,
        budget=body.budget,
        context=body.context,
        locked_pieces=body.locked_pieces,
        custom_label=body.custom_label,
        brand_tier=body.brand_tier,
        user_hint=body.user_hint,
    )
    if not result.get("piece"):
        raise HTTPException(status_code=404, detail="No alternative found. Try again.")
    return result
