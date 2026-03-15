"""
Price checker service.

Daily cron job calls run_price_checks() which:
  1. Loads all active alerts from PostgreSQL.
  2. Queries Serper Shopping for current price by product title + domain match.
  3. Sends a Resend.com email when price drops.
  4. Updates last_price / last_checked in the database.
"""

import re
from typing import Optional
from urllib.parse import urlparse

import requests
import resend

from app.config import get_settings
from app.core.alerts_db import get_active_alerts, update_price
from app.core.logging import logger

settings = get_settings()
resend.api_key = settings.resend_api_key


# ── Helpers ────────────────────────────────────────────────────────────────


def _parse_price(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.]", "", str(value).replace(",", ""))
    return float(cleaned) if cleaned else None


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


# ── Price fetching ─────────────────────────────────────────────────────────


def _fetch_current_price(title: str, product_url: str) -> Optional[float]:
    """Query Serper Shopping for the current price of a product."""
    try:
        resp = requests.post(
            "https://google.serper.dev/shopping",
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            json={"q": title[:100], "num": 5, "gl": "in"},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("shopping", [])

        # Prefer a result from the same domain (most accurate match)
        domain = _extract_domain(product_url)
        for item in items:
            if domain and domain in item.get("link", ""):
                price = _parse_price(item.get("price"))
                if price:
                    return price

        # Fallback: first result price
        if items:
            return _parse_price(items[0].get("price"))

    except Exception as e:
        logger.warning(f"[PriceChecker] Price fetch failed for '{title[:40]}': {e}")

    return None


# ── Email ──────────────────────────────────────────────────────────────────


def _send_price_drop_email(
    email: str,
    title: str,
    old_price: float,
    new_price: float,
    product_url: str,
    image_url: str,
    currency: str,
) -> None:
    """Send a styled price-drop alert email via Resend."""
    try:
        sym = "₹" if currency == "INR" else "$"
        drop_pct = round((old_price - new_price) / old_price * 100)
        img_tag = (
            f'<img src="{image_url}" '
            f'style="width:120px;height:150px;object-fit:cover;border-radius:8px;'
            f'margin-bottom:20px;display:block;" />'
            if image_url else ""
        )

        html = f"""
        <div style="font-family:Georgia,serif;max-width:600px;margin:0 auto;color:#1A1A1A;">
          <div style="background:#1A1A1A;padding:24px 32px;">
            <h1 style="color:#C9A84C;margin:0;font-size:22px;letter-spacing:2px;">
              PRICE DROP ALERT
            </h1>
            <p style="color:#F5F0E8;margin:4px 0 0;font-size:13px;">
              Your saved item just got cheaper
            </p>
          </div>

          <div style="padding:32px;background:#F5F0E8;">
            {img_tag}
            <h2 style="margin:0 0 16px;font-size:18px;line-height:1.4;">{title}</h2>

            <table style="border-collapse:collapse;">
              <tr>
                <td style="padding-right:24px;">
                  <p style="margin:0;font-size:11px;color:#999;text-transform:uppercase;">Was</p>
                  <p style="margin:4px 0 0;font-size:18px;text-decoration:line-through;color:#999;">
                    {sym}{old_price:,.0f}
                  </p>
                </td>
                <td style="padding-right:24px;">
                  <p style="margin:0;font-size:11px;color:#C9A84C;text-transform:uppercase;">Now</p>
                  <p style="margin:4px 0 0;font-size:24px;font-weight:bold;color:#1A1A1A;">
                    {sym}{new_price:,.0f}
                  </p>
                </td>
                <td>
                  <div style="background:#C9A84C;color:#fff;padding:6px 14px;
                              border-radius:20px;font-size:14px;font-weight:bold;">
                    -{drop_pct}%
                  </div>
                </td>
              </tr>
            </table>

            <a href="{product_url}"
               style="display:inline-block;margin-top:28px;background:#1A1A1A;
                      color:#F5F0E8;padding:12px 28px;text-decoration:none;
                      border-radius:4px;font-size:13px;letter-spacing:1.5px;">
              SHOP NOW
            </a>
          </div>

          <div style="padding:16px 32px;background:#1A1A1A;">
            <p style="margin:0;font-size:11px;color:#555;text-align:center;">
              You saved this item in your FashionAI wishlist.
              Prices are checked daily — we only email when a drop is detected.
            </p>
          </div>
        </div>
        """

        resend.Emails.send({
            "from":    settings.resend_from_email,
            "to":      email,
            "subject": f"Price Drop! {title[:50]} → {sym}{new_price:,.0f} ({drop_pct}% off)",
            "html":    html,
        })
        logger.info(
            f"[PriceChecker] Email sent → {email} | '{title[:35]}' "
            f"{sym}{old_price:.0f} → {sym}{new_price:.0f}"
        )

    except Exception as e:
        logger.error(f"[PriceChecker] Email failed for {email}: {e}")


# ── Main cron entry point ──────────────────────────────────────────────────


def run_price_checks() -> None:
    """
    Called daily by APScheduler.
    Checks all active alerts and emails users when price drops.
    """
    alerts = get_active_alerts()
    logger.info(f"[PriceChecker] Starting — {len(alerts)} active alert(s)")

    checked = drops = 0

    for alert in alerts:
        title       = alert.get("title", "")
        product_url = alert.get("product_url", "")
        old_price   = alert.get("last_price")

        current_price = _fetch_current_price(title, product_url)
        if current_price is None:
            continue

        update_price(alert["id"], current_price)
        checked += 1

        if old_price is not None and current_price < old_price:
            _send_price_drop_email(
                email=alert["email"],
                title=title,
                old_price=old_price,
                new_price=current_price,
                product_url=product_url,
                image_url=alert.get("image_url", ""),
                currency=alert.get("currency", "INR"),
            )
            drops += 1

    logger.info(f"[PriceChecker] Done — {checked} checked, {drops} drop(s) notified")
