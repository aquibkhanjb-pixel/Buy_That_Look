"""Admin dashboard endpoints — requires is_admin JWT claim."""

from datetime import date, datetime, timedelta
from typing import Optional
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import require_admin, create_access_token
from app.core.logging import logger
from app.db.database import get_db
from app.db.models import User, Subscription, WishlistItem, UserUsage, ChatMessage
from app.core.alerts_db import _engine as alerts_engine
from sqlalchemy import text

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _active_alert_count(db: Session) -> int:
    try:
        with alerts_engine.connect() as conn:
            row = conn.execute(text("SELECT COUNT(*) FROM price_alerts")).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Overall dashboard statistics."""
    today = date.today()
    week_ago = datetime.utcnow() - timedelta(days=7)

    total_users   = db.query(func.count(User.id)).scalar() or 0
    premium_users = db.query(func.count(User.id)).filter(User.tier == "premium").scalar() or 0
    free_users    = total_users - premium_users

    price_row = db.execute(text("SELECT value FROM app_settings WHERE key = 'subscription_price'")).fetchone()
    subscription_price = int(price_row[0]) if price_row else 25
    mrr = premium_users * subscription_price

    new_today = db.query(func.count(User.id)).filter(
        func.date(User.created_at) == today
    ).scalar() or 0

    new_this_week = db.query(func.count(User.id)).filter(
        User.created_at >= week_ago
    ).scalar() or 0

    chats_today = db.query(func.sum(UserUsage.chat_count)).filter(
        UserUsage.date == today
    ).scalar() or 0

    occasion_today = db.query(func.sum(UserUsage.occasion_count)).filter(
        UserUsage.date == today
    ).scalar() or 0

    total_wishlist = db.query(func.count(WishlistItem.id)).scalar() or 0
    total_alerts   = _active_alert_count(db)

    return {
        "total_users":      total_users,
        "premium_users":    premium_users,
        "free_users":       free_users,
        "mrr":              mrr,
        "new_today":        new_today,
        "new_this_week":    new_this_week,
        "chats_today":      int(chats_today),
        "occasion_today":   int(occasion_today),
        "total_wishlist":   total_wishlist,
        "total_alerts":     total_alerts,
    }


# ── Users list ────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    tier: Optional[str] = None,
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Paginated list of all users with usage stats."""
    today = date.today()

    query = db.query(User)
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) | (User.name.ilike(f"%{search}%"))
        )
    if tier:
        query = query.filter(User.tier == tier)

    total = query.count()
    users = query.order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    result = []
    for u in users:
        usage = db.query(UserUsage).filter(
            UserUsage.user_id == u.id,
            UserUsage.date == today,
        ).first()

        wishlist_count = db.query(func.count(WishlistItem.id)).filter(
            WishlistItem.user_id == u.id
        ).scalar() or 0

        result.append({
            "id":             str(u.id),
            "email":          u.email,
            "name":           u.name or "",
            "avatar_url":     u.avatar_url or "",
            "tier":           u.tier,
            "is_admin":       u.is_admin,
            "created_at":     u.created_at.isoformat() if u.created_at else None,
            "chats_today":    usage.chat_count if usage else 0,
            "occasions_today":usage.occasion_count if usage else 0,
            "wishlist_count": wishlist_count,
        })

    return {
        "users": result,
        "total": total,
        "page":  page,
        "pages": max(1, (total + limit - 1) // limit),
    }


# ── Tier override ─────────────────────────────────────────────────────────────

class TierUpdate(BaseModel):
    tier: str  # "free" | "premium"


@router.patch("/users/{user_id}/tier")
def update_user_tier(
    user_id: str,
    body: TierUpdate,
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Manually upgrade or downgrade a user's tier."""
    if body.tier not in ("free", "premium"):
        raise HTTPException(status_code=422, detail="tier must be 'free' or 'premium'")

    user = db.query(User).filter(User.id == _uuid.UUID(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.tier = body.tier
    db.commit()
    logger.info(f"[Admin] {_admin['email']} set {user.email} → tier={body.tier}")
    return {"ok": True, "user_id": user_id, "tier": body.tier}


# ── Admin toggle ──────────────────────────────────────────────────────────────

class AdminToggle(BaseModel):
    is_admin: bool


@router.patch("/users/{user_id}/admin")
def update_user_admin(
    user_id: str,
    body: AdminToggle,
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Promote or demote a user's admin status."""
    user = db.query(User).filter(User.id == _uuid.UUID(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if str(user.id) == _admin["sub"]:
        raise HTTPException(status_code=403, detail="Cannot change your own admin status")

    user.is_admin = body.is_admin
    db.commit()
    action = "promoted to admin" if body.is_admin else "demoted from admin"
    logger.info(f"[Admin] {_admin['email']} {action}: {user.email}")
    return {"ok": True, "user_id": user_id, "is_admin": body.is_admin}


# ── Delete user ───────────────────────────────────────────────────────────────

@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Permanently delete a user and all their data (cascade)."""
    user = db.query(User).filter(User.id == _uuid.UUID(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_admin:
        raise HTTPException(status_code=403, detail="Cannot delete an admin user")

    email = user.email
    db.delete(user)
    db.commit()
    logger.info(f"[Admin] {_admin['email']} deleted user {email}")
    return {"ok": True, "deleted": email}


# ── User growth chart ──────────────────────────────────────────────────────────

@router.get("/growth")
def user_growth(
    days: int = 30,
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Daily new user signups for the last N days (for the admin chart)."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    rows = db.query(
        func.date(User.created_at).label("day"),
        func.count(User.id).label("count"),
    ).filter(
        User.created_at >= cutoff
    ).group_by(
        func.date(User.created_at)
    ).order_by(
        func.date(User.created_at)
    ).all()

    today = date.today()
    data = {row.day: row.count for row in rows}

    result = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        result.append({"date": d.isoformat(), "count": data.get(d, 0)})
    return result


# ── Price Alerts management ────────────────────────────────────────────────────

@router.get("/alerts")
def list_all_alerts(
    page: int = 1,
    limit: int = 20,
    _admin: dict = Depends(require_admin),
):
    """Paginated list of all active price alerts across all users."""
    try:
        with alerts_engine.connect() as conn:
            total_row = conn.execute(
                text("SELECT COUNT(*) FROM price_alerts WHERE is_active = TRUE")
            ).fetchone()
            total = total_row[0] if total_row else 0

            rows = conn.execute(
                text("""
                    SELECT id, email, title, product_url, image_url,
                           last_price, currency, source_site, created_at, last_checked
                    FROM price_alerts
                    WHERE is_active = TRUE
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": limit, "offset": (page - 1) * limit},
            ).mappings().all()

        alerts = []
        for r in rows:
            d = dict(r)
            d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
            d["last_checked"] = d["last_checked"].isoformat() if d.get("last_checked") else None
            alerts.append(d)

        return {
            "alerts": alerts,
            "total": total,
            "page": page,
            "pages": max(1, (total + limit - 1) // limit),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts/{alert_id}")
def admin_delete_alert(
    alert_id: int,
    _admin: dict = Depends(require_admin),
):
    """Hard-delete a price alert by ID."""
    try:
        with alerts_engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM price_alerts WHERE id = :id"),
                {"id": alert_id},
            )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alert not found")
        logger.info(f"[Admin] {_admin['email']} deleted alert {alert_id}")
        return {"ok": True, "deleted": alert_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── App Settings ───────────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    subscription_price: int


@router.get("/settings")
def get_admin_settings(
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get all app settings."""
    rows = db.execute(text("SELECT key, value FROM app_settings")).all()
    return {row[0]: row[1] for row in rows}


@router.patch("/settings")
def update_admin_settings(
    body: SettingsUpdate,
    _admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update app settings (e.g. subscription price)."""
    if body.subscription_price < 1:
        raise HTTPException(status_code=422, detail="Price must be at least ₹1")

    db.execute(
        text("""
            INSERT INTO app_settings (key, value)
            VALUES ('subscription_price', :value)
            ON CONFLICT (key) DO UPDATE SET value = :value
        """),
        {"value": str(body.subscription_price)},
    )
    db.commit()
    logger.info(f"[Admin] {_admin['email']} set subscription_price → ₹{body.subscription_price}")
    return {"ok": True, "subscription_price": body.subscription_price}
