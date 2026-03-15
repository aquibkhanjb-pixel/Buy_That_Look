"""
Razorpay payment endpoints.

Flow:
  1. POST /checkout  → create Razorpay subscription → return {subscription_id, key_id}
  2. Frontend opens  → Razorpay checkout modal (checkout.js)
  3. User pays       → Razorpay calls handler with {payment_id, subscription_id, signature}
  4. POST /verify    → backend verifies HMAC → sets user.tier = premium → returns new JWT
  5. POST /cancel    → cancel active subscription → sets user.tier = free
  6. POST /webhook   → (optional) Razorpay server-side events for robustness
"""

import hashlib
import hmac
import json

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth import create_access_token, get_current_user
from app.core.logging import logger
from app.db.database import get_db
from app.db.models import Subscription, User

settings = get_settings()

_rz = razorpay.Client(
    auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
)

router = APIRouter()


# ── Checkout ───────────────────────────────────────────────────────────────


@router.post("/checkout")
def create_checkout(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a Razorpay Subscription and return the details needed
    for the frontend checkout.js modal.
    """
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.tier == "premium":
        raise HTTPException(status_code=400, detail="Already subscribed to Premium")

    try:
        subscription = _rz.subscription.create({
            "plan_id":     settings.razorpay_plan_id,
            "total_count": 12,          # 12 monthly billing cycles
            "quantity":    1,
            "notify_info": {
                "notify_phone": None,
                "notify_email": user.email,
            },
        })
    except Exception as e:
        logger.error(f"[Razorpay] Subscription create failed: {e}")
        raise HTTPException(status_code=502, detail="Payment gateway error. Please try again.")

    logger.info(f"[Razorpay] Subscription created: {subscription['id']} for {user.email}")

    return {
        "subscription_id": subscription["id"],
        "key_id":          settings.razorpay_key_id,
        "user_name":       user.name or "",
        "user_email":      user.email,
    }


# ── Verify (called by frontend after successful payment) ───────────────────


class VerifyRequest(BaseModel):
    razorpay_payment_id:    str
    razorpay_subscription_id: str
    razorpay_signature:     str


@router.post("/verify")
def verify_payment(
    body: VerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Verify Razorpay HMAC signature, activate premium tier, return refreshed JWT.
    Called from frontend handler after checkout.js success callback.
    """
    # Verify signature
    expected = hmac.new(
        settings.razorpay_key_secret.encode(),
        f"{body.razorpay_payment_id}|{body.razorpay_subscription_id}".encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, body.razorpay_signature):
        raise HTTPException(status_code=400, detail="Payment verification failed — invalid signature")

    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Activate premium
    user.tier = "premium"
    db.commit()

    # Upsert subscription record
    sub = db.query(Subscription).filter(
        Subscription.razorpay_subscription_id == body.razorpay_subscription_id
    ).first()
    if not sub:
        sub = Subscription(
            user_id=user.id,
            razorpay_subscription_id=body.razorpay_subscription_id,
            plan_id=settings.razorpay_plan_id,
            status="active",
        )
        db.add(sub)
    else:
        sub.status = "active"
    db.commit()

    logger.info(f"[Razorpay] Payment verified → {user.email} is now Premium")

    # Return fresh JWT with updated tier so frontend can update session immediately
    new_token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        tier="premium",
    )
    return {"access_token": new_token, "tier": "premium"}


# ── Cancel ─────────────────────────────────────────────────────────────────


@router.post("/cancel")
def cancel_subscription(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel the user's active Razorpay subscription."""
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user or user.tier != "premium":
        raise HTTPException(status_code=400, detail="No active subscription found")

    sub = db.query(Subscription).filter(
        Subscription.user_id == user.id,
        Subscription.status == "active",
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription record not found")

    try:
        _rz.subscription.cancel(sub.razorpay_subscription_id, {"cancel_at_cycle_end": 1})
    except Exception as e:
        logger.error(f"[Razorpay] Cancel failed: {e}")
        raise HTTPException(status_code=502, detail="Could not cancel subscription. Please try again.")

    sub.status = "cancelled"
    user.tier  = "free"
    db.commit()

    logger.info(f"[Razorpay] Subscription cancelled for {user.email}")

    new_token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        tier="free",
    )
    return {"status": "cancelled", "access_token": new_token, "tier": "free"}


# ── Webhook (server-side robustness) ───────────────────────────────────────


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Razorpay webhook events.
    Register at: dashboard.razorpay.com → Settings → Webhooks
    Events: subscription.activated, subscription.halted, subscription.cancelled
    """
    body      = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    # Verify webhook signature
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    evt = event.get("event", "")
    payload = event.get("payload", {}).get("subscription", {}).get("entity", {})
    sub_id  = payload.get("id")

    if not sub_id:
        return {"status": "ignored"}

    sub = db.query(Subscription).filter(
        Subscription.razorpay_subscription_id == sub_id
    ).first()

    if evt == "subscription.activated":
        if sub:
            sub.status = "active"
            user = db.query(User).filter(User.id == sub.user_id).first()
            if user:
                user.tier = "premium"
        db.commit()
        logger.info(f"[Razorpay Webhook] subscription.activated → {sub_id}")

    elif evt in ("subscription.halted", "subscription.cancelled"):
        if sub:
            sub.status = "halted" if "halted" in evt else "cancelled"
            user = db.query(User).filter(User.id == sub.user_id).first()
            if user:
                user.tier = "free"
        db.commit()
        logger.info(f"[Razorpay Webhook] {evt} → {sub_id}")

    return {"status": "ok"}
