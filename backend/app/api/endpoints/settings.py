"""Public app settings endpoint (no auth required)."""

from fastapi import APIRouter
from sqlalchemy import text
from app.db.database import engine

router = APIRouter()


@router.get("")
def get_settings():
    """Return public app settings (e.g. subscription_price)."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT key, value FROM app_settings")).all()
        return {row[0]: row[1] for row in rows}
    except Exception:
        return {"subscription_price": "25"}
