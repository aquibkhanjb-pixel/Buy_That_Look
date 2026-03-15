# FashionAI — Free vs Premium Feature Comparison

> Current implementation status as of 2026-03-15

---

## Pricing

| | Free | Premium |
|---|---|---|
| **Price** | ₹0 — forever | ₹99/month |
| **Payment** | — | Card, UPI, Netbanking (Razorpay) |
| **Cancel anytime** | — | ✅ |

---

## AI Chat Assistant

| Feature | Free | Premium | Notes |
|---|---|---|---|
| **AI chat messages** | 15 / day | Unlimited | Counter resets daily at midnight |
| **Text-based fashion queries** | ✅ | ✅ | Powered by Gemini 2.5 Flash Lite |
| **Image upload in chat** | ✅ | ✅ | Visual search via Google Lens + Serper |
| **Multi-turn conversation** | ✅ | ✅ | Session memory across turns |
| **Slot-filling clarification** | ✅ | ✅ | Asks one focused follow-up question |
| **Outfit completion ("Complete the Look")** | ✅ | ✅ | ReAct subgraph finds matching pieces |
| **Feedback refinement** | ✅ | ✅ | "Show me something cheaper / different" |

---

## Product Search

| Feature | Free | Premium | Notes |
|---|---|---|---|
| **Web product search** | ✅ | ✅ | Serper text search |
| **Google Lens visual search** | ✅ | ✅ | Upload image → find similar products |
| **Visual web search** | ✅ | ✅ | Image description → Serper search |
| **Find This Look** | ✅ | ✅ | URL or upload → similar products |
| **Direct platform links** | ✅ | ✅ | Myntra, Ajio, Amazon, Flipkart, Meesho |

---

## Wishlist

| Feature | Free | Premium | Notes |
|---|---|---|---|
| **Save products** | Up to 20 items | Unlimited | Stored in PostgreSQL, scoped per user |
| **Synced across devices** | ✅ | ✅ | DB-backed, not localStorage |
| **Per-user (not shared)** | ✅ | ✅ | Isolated by Google account |
| **Remove items** | ✅ | ✅ | |

---

## Price Drop Alerts

| Feature | Free | Premium | Notes |
|---|---|---|---|
| **Active price alerts** | Up to 3 | Unlimited | Tracked in PostgreSQL |
| **Daily price check** | ✅ | ✅ | Runs at 09:00 IST via APScheduler |
| **Email notification on price drop** | ✅ | ✅ | Sent via Resend.com |
| **View tracked items** | ✅ | ✅ | Price Tracking tab in Wishlist panel |
| **Remove alerts** | ✅ | ✅ | Soft-delete (is_active = FALSE) |

---

## Virtual Try-On

| Feature | Free | Premium | Notes |
|---|---|---|---|
| **Virtual try-on** | ❌ | ✅ | IDM-VTON on HuggingFace (~40s) |
| **Upgrade prompt shown** | ✅ | — | Crown gate in TryOnModal |

---

## Fashion Trends

| Feature | Free | Premium | Notes |
|---|---|---|---|
| **Trend discovery** | ✅ | ✅ | 6 trending styles, updated every hour |
| **Click-to-search trend** | ✅ | ✅ | Launches chat with trend query |

---

## Account & Auth

| Feature | Free | Premium | Notes |
|---|---|---|---|
| **Google Sign-In** | ✅ | ✅ | NextAuth.js v4 |
| **Secure JWT session** | ✅ | ✅ | HS256, 30-day expiry |
| **Tier badge in header** | — | Crown badge | Shown in UserMenu dropdown |
| **Upgrade from app** | — | ✅ | /pricing page → Razorpay modal |
| **Cancel subscription** | — | ✅ | /pricing page → confirm dialog |

---

## Enforcement Status

| Limit | Where Enforced | Status |
|---|---|---|
| Chat 15/day | Backend (`chat.py` + `UserUsage` table) + Frontend (upgrade msg on 403) | ✅ Live |
| Wishlist 20 items | Backend (`wishlist.py` returns 403) + Frontend (amber banner) | ✅ Live |
| Price alerts 3 items | Backend (`alerts.py` checks count before insert) | ✅ Live |
| Virtual try-on (Premium only) | Backend (`require_premium` dependency on `/tryon/`) + Frontend (upgrade gate in modal) | ✅ Live |

---

## Features Planned / Not Yet Built

| Feature | Notes |
|---|---|
| **Chat history (30-day)** | Listed in pricing page UI but not yet stored/retrieved |
| **Style memory across sessions** | Listed in pricing page UI but not yet implemented |
| **Priority product results** | Listed in pricing page UI — no backend differentiation yet |
| **Razorpay live mode** | Currently test mode only (live requires business website URL) |
| **Webhook-based tier sync** | `RAZORPAY_WEBHOOK_SECRET` not set — `/verify` handles payment confirmation instead |
