"""User management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.auth import create_access_token, get_current_user
from app.db.database import get_db
from app.db.models import User

router = APIRouter()


class UserSyncRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    avatar_url: str | None = None


@router.post("/sync")
def sync_user(body: UserSyncRequest, db: Session = Depends(get_db)):
    """
    Called server-side by NextAuth after Google login.
    Creates the user if this is their first visit.
    Returns a signed backend JWT and the user's tier.
    """
    from app.config import get_settings
    settings = get_settings()

    user = db.query(User).filter(User.email == str(body.email)).first()
    is_admin = str(body.email) in settings.admin_email_list

    if not user:
        user = User(
            email=str(body.email),
            name=body.name,
            avatar_url=body.avatar_url,
            is_admin=is_admin,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif is_admin and not user.is_admin:
        # Email is in ADMIN_EMAILS but DB flag is off → grant admin
        user.is_admin = True
        db.commit()
    # Note: we do NOT revoke is_admin here — admins promoted via the dashboard
    # keep their status even if not listed in ADMIN_EMAILS.

    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        tier=user.tier,
        is_admin=user.is_admin,
    )
    return {"access_token": token, "tier": user.tier, "user_id": str(user.id), "is_admin": user.is_admin}


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the current user's profile and tier (always fresh from DB)."""
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id":         str(user.id),
        "email":      user.email,
        "name":       user.name,
        "avatar_url": user.avatar_url,
        "tier":       user.tier,
    }


@router.post("/refresh-token")
def refresh_token(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Re-issue JWT with latest tier from DB.
    Called by frontend after successful Stripe payment to pick up 'premium' tier.
    """
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        tier=user.tier,
    )
    return {"access_token": token, "tier": user.tier}
