"""
PostgreSQL database for price drop alerts.
Uses SQLAlchemy Core (no ORM) — text queries, simple and fast.
Table is auto-created on first startup via init_alerts_db().
"""

import re
from typing import List, Optional

from sqlalchemy import create_engine, text

from app.config import get_settings

_settings = get_settings()
_engine = create_engine(_settings.database_url, pool_pre_ping=True)


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS price_alerts (
    id           SERIAL PRIMARY KEY,
    email        TEXT    NOT NULL,
    product_url  TEXT    NOT NULL,
    product_id   TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    image_url    TEXT    DEFAULT '',
    last_price   DOUBLE PRECISION,
    currency     TEXT    DEFAULT 'INR',
    source_site  TEXT    DEFAULT '',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    last_checked TIMESTAMPTZ,
    is_active    BOOLEAN DEFAULT TRUE,
    CONSTRAINT uq_email_product_url UNIQUE (email, product_url)
);
"""


def init_alerts_db() -> None:
    """Create the price_alerts table if it doesn't exist."""
    with _engine.begin() as conn:
        conn.execute(text(_CREATE_TABLE))


def _parse_price(price) -> Optional[float]:
    if price is None:
        return None
    if isinstance(price, (int, float)):
        return float(price)
    if isinstance(price, str):
        cleaned = re.sub(r"[^\d.]", "", price.replace(",", ""))
        return float(cleaned) if cleaned else None
    return None


def add_alerts(email: str, products: List[dict]) -> int:
    """
    Insert or update price alerts for a list of products.
    Returns count of affected rows.
    """
    inserted = 0
    with _engine.begin() as conn:
        for p in products:
            price = _parse_price(p.get("price"))
            try:
                result = conn.execute(
                    text("""
                        INSERT INTO price_alerts
                            (email, product_url, product_id, title, image_url,
                             last_price, currency, source_site)
                        VALUES
                            (:email, :product_url, :product_id, :title, :image_url,
                             :last_price, :currency, :source_site)
                        ON CONFLICT (email, product_url) DO UPDATE SET
                            is_active    = TRUE,
                            last_price   = COALESCE(EXCLUDED.last_price, price_alerts.last_price),
                            last_checked = NULL
                    """),
                    {
                        "email":       email,
                        "product_url": p.get("product_url", ""),
                        "product_id":  p.get("id") or p.get("product_url", ""),
                        "title":       p.get("title", ""),
                        "image_url":   p.get("image_url", ""),
                        "last_price":  price,
                        "currency":    p.get("currency", "INR"),
                        "source_site": p.get("source_site", ""),
                    },
                )
                inserted += result.rowcount
            except Exception:
                continue
    return inserted


def get_active_alerts() -> List[dict]:
    """Return all active price alerts (used by the daily cron job)."""
    with _engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM price_alerts WHERE is_active = TRUE")
        ).mappings().all()
    return [dict(r) for r in rows]


def update_price(alert_id: int, new_price: Optional[float]) -> None:
    """Update last_price and last_checked timestamp after a price check."""
    with _engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE price_alerts
                SET last_price = :price, last_checked = NOW()
                WHERE id = :id
            """),
            {"price": new_price, "id": alert_id},
        )


def deactivate_alert(email: str, product_url: str) -> None:
    """Soft-delete an alert (sets is_active = FALSE)."""
    with _engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE price_alerts
                SET is_active = FALSE
                WHERE email = :email AND product_url = :url
            """),
            {"email": email, "url": product_url},
        )


def get_alerts_for_email(email: str) -> List[dict]:
    """Return active alerts for a specific user email."""
    with _engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM price_alerts WHERE email = :email AND is_active = TRUE"),
            {"email": email},
        ).mappings().all()
    return [dict(r) for r in rows]
