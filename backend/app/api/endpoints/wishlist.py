"""User wishlist — DB-backed, scoped by authenticated user."""

from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import get_db
from app.db.models import WishlistItem

router = APIRouter()

FREE_WISHLIST_LIMIT = 20


class WishlistAddRequest(BaseModel):
    product_id: str
    title: str
    product_url: Optional[str] = ""
    image_url: Optional[str] = ""
    price: Optional[float] = None
    currency: Optional[str] = "INR"
    source_site: Optional[str] = ""
    description: Optional[str] = None
    brand: Optional[str] = None


@router.get("/")
def get_wishlist(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all wishlist items for the authenticated user."""
    items = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user["sub"])
        .order_by(WishlistItem.created_at.desc())
        .all()
    )
    return {"items": [_serialize(i) for i in items], "count": len(items)}


@router.post("/")
def add_to_wishlist(
    body: WishlistAddRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a product to the authenticated user's wishlist. Free tier: max 20 items."""
    user_id = user["sub"]
    tier = user.get("tier", "free")

    # Check if already wishlisted
    existing = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user_id, WishlistItem.product_id == body.product_id)
        .first()
    )
    if existing:
        return {"item": _serialize(existing), "added": False}

    # Free tier limit
    if tier != "premium":
        count = db.query(WishlistItem).filter(WishlistItem.user_id == user_id).count()
        if count >= FREE_WISHLIST_LIMIT:
            raise HTTPException(
                status_code=403,
                detail=f"Free tier allows up to {FREE_WISHLIST_LIMIT} wishlist items. Upgrade to Premium for unlimited.",
            )

    item = WishlistItem(
        user_id=user_id,
        product_id=body.product_id,
        title=body.title,
        product_url=body.product_url or "",
        image_url=body.image_url or "",
        price=body.price,
        currency=body.currency or "INR",
        source_site=body.source_site or "",
        description=body.description,
        brand=body.brand,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"item": _serialize(item), "added": True}


@router.delete("/{product_id}")
def remove_from_wishlist(
    product_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a product from the authenticated user's wishlist."""
    item = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user["sub"], WishlistItem.product_id == product_id)
        .first()
    )
    if item:
        db.delete(item)
        db.commit()
    return {"status": "removed"}


def _serialize(item: WishlistItem) -> dict:
    return {
        "id":          item.id,
        "product_id":  item.product_id,
        "title":       item.title,
        "product_url": item.product_url,
        "image_url":   item.image_url,
        "price":       item.price,
        "currency":    item.currency,
        "source_site": item.source_site,
        "description": item.description,
        "brand":       item.brand,
        "created_at":  item.created_at.isoformat() if item.created_at else None,
    }
