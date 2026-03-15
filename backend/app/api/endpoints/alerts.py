"""Price drop alert endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from app.core.alerts_db import add_alerts, deactivate_alert, get_alerts_for_email
from app.core.auth import get_current_user
from app.core.logging import logger

router = APIRouter()

FREE_ALERTS_LIMIT = 3

_optional_bearer = HTTPBearer(auto_error=False)


def _get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> Optional[dict]:
    if credentials is None:
        return None
    try:
        return get_current_user(credentials)
    except Exception:
        return None


class ProductAlert(BaseModel):
    id: Optional[str] = None
    product_url: str
    title: str
    price: Optional[float] = None
    image_url: Optional[str] = ""
    currency: Optional[str] = "INR"
    source_site: Optional[str] = ""


class RegisterAlertsRequest(BaseModel):
    email: EmailStr
    products: List[ProductAlert]


class DeleteAlertRequest(BaseModel):
    email: EmailStr
    product_url: str


@router.post("/register")
def register_alerts(
    body: RegisterAlertsRequest,
    current_user: Optional[dict] = Depends(_get_optional_user),
):
    """
    Register one or more wishlist products for price drop monitoring.
    Existing entries are upserted (reactivated + price updated).
    Free tier: max 3 active alerts.
    """
    if not body.products:
        raise HTTPException(status_code=422, detail="No products provided")

    # Free tier limit check
    if current_user and current_user.get("tier", "free") != "premium":
        existing = get_alerts_for_email(str(body.email))
        if len(existing) >= FREE_ALERTS_LIMIT:
            raise HTTPException(
                status_code=403,
                detail=f"Free tier allows up to {FREE_ALERTS_LIMIT} price alerts. Upgrade to Premium for unlimited.",
            )

    products_dicts = [p.model_dump() for p in body.products]
    count = add_alerts(str(body.email), products_dicts)
    logger.info(f"[Alerts] {count} alert(s) registered for {body.email}")

    return {
        "status":     "ok",
        "registered": count,
        "email":      str(body.email),
        "total":      len(body.products),
    }


@router.delete("/")
def delete_alert(body: DeleteAlertRequest):
    """Deactivate a specific price alert (soft delete)."""
    deactivate_alert(str(body.email), body.product_url)
    return {"status": "deactivated"}


@router.get("/{email}")
def get_alerts(email: str):
    """Return all active price alerts for an email address."""
    alerts = get_alerts_for_email(email)
    return {"email": email, "alerts": alerts, "count": len(alerts)}
