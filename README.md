# StyleAI — AI-Powered Fashion Recommendation Platform

A full-stack AI fashion assistant that helps users discover outfits, plan occasion-based looks, track prices, and virtually try on clothes — powered by Google Gemini and real-time product search.

---

## Features

### AI Chat Assistant
- Conversational fashion search using a LangGraph multi-node graph (intent detection → feature extraction → web search → response generation)
- Understands gender, budget, color, style, and occasion from natural language
- ReAct outfit completion subgraph — recommends complementary pieces (footwear, accessories, bottom wear) for any reference garment
- Persistent chat history for premium users (30-day retention)
- 15 chats/day on free tier, unlimited on premium

### Visual Search (Google Lens + Serper.dev)
- Upload any outfit image → finds visually similar products from Indian fashion platforms
- Gemini Vision verification layer rejects mismatched results before showing them
- ReAct retry loop refines the search query if fewer than 3 good results are found

### Occasion Planner
- Describe any occasion → AI extracts context (formality, gender, budget, role) and asks which clothing categories to include
- Builds a complete outfit using real Serper product search — no hallucinated products
- Pairwise compatibility graph: every item pair scored by Gemini Vision (green/amber/red)
- Swap any piece with a hinted alternative (e.g. "something darker in blue")
- Budget tracker: total vs target with color coding
- Free: 2 outfit plans/day | Premium: unlimited

### Virtual Try-On
- Upload your photo + a garment image → HuggingFace IDM-VTON model composites them
- Premium users only

### Trend Analyzer
- Discovers trending styles from Indian fashion feeds
- One-click search from trend cards into the AI chat

### Find This Look
- Upload a full outfit photo → identifies individual pieces → links to each on e-commerce platforms

### Wishlist
- Save any product across sessions (DB-backed, synced across devices)
- Free: 20 items | Premium: unlimited

### Price Drop Alerts
- Select wishlist items → enter email → get notified when price drops
- Daily APScheduler cron job checks prices via Serper, sends branded emails via Resend.com
- Free: 3 alerts | Premium: unlimited

### User Auth + Subscriptions
- Google OAuth via NextAuth.js
- Backend JWT (HS256, 30-day expiry)
- Razorpay live payments — ₹25/month recurring (Card, UPI, Netbanking)
- Webhook-driven tier upgrades/downgrades

### Admin Dashboard
- Stats: total users, premium users, MRR, signups today/this week, chats, occasions
- User growth bar chart (last 14 days)
- User management: tier toggle, admin promotion, delete (with confirmation dialogs)
- Price alerts management
- Dynamic subscription price (stored in DB, no redeploy needed)
- Export users as CSV

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Backend | FastAPI (Python 3.10), SQLAlchemy ORM |
| AI / LLM | Google Gemini 2.5 Flash (chat, vision, query generation) |
| Product Search | Serper.dev (Google Shopping + Google Lens API) |
| Database | PostgreSQL (Neon serverless) |
| Auth | NextAuth.js v4 (Google OAuth) + JWT |
| Payments | Razorpay (live mode, recurring subscriptions) |
| Email | Resend.com |
| Scheduler | APScheduler (daily price checks at 09:00 IST) |
| Virtual Try-On | HuggingFace IDM-VTON |
| Error Monitoring | Sentry (frontend + backend) |
| Deployment | Render (backend), Vercel (frontend) |

---

## Architecture

```
User
 │
 ├─ Next.js Frontend (Vercel)
 │    ├─ NextAuth Google OAuth → syncs with backend → gets JWT
 │    ├─ AI Chat (streaming via /api/v1/chat/)
 │    ├─ Occasion Planner (3-step: context → categories → outfit)
 │    ├─ Visual Search (image upload → Lens + Serper)
 │    ├─ Virtual Try-On (IDM-VTON)
 │    ├─ Wishlist + Price Alerts
 │    └─ Admin Dashboard (/admin — server-guarded)
 │
 └─ FastAPI Backend (Render)
      ├─ LangGraph Chat Pipeline
      │    intent → extract_features → web_search → generate_response
      │                                    │
      │                              Serper.dev Shopping
      │                              (domain-filtered: Myntra/Ajio/Amazon/Flipkart/Meesho)
      │                              Gemini Vision verification
      │
      ├─ Occasion Service
      │    context extraction → category MCQ → parallel Serper search
      │    → pairwise compatibility graph (Gemini Vision) → ReAct judge loop
      │
      ├─ PostgreSQL (Neon)
      │    users, subscriptions, wishlist_items, user_usage,
      │    chat_sessions, chat_messages, price_alerts, app_settings
      │
      └─ APScheduler (daily 09:00 IST)
           price check (Serper) → Resend email on drop
```

---

## Project Structure

```
Fashion_Recommendation/
├── backend/
│   ├── app/
│   │   ├── api/endpoints/      # chat, occasion, tryon, wishlist, alerts,
│   │   │                       # payments, users, admin, settings, health
│   │   ├── core/               # auth.py, database.py, scheduler.py, alerts_db.py
│   │   ├── db/                 # SQLAlchemy ORM models + engine
│   │   ├── services/           # chat_service.py, occasion_service.py,
│   │   │                       # tryon_service.py, price_checker.py, llm_service.py
│   │   ├── schemas/            # Pydantic request/response models
│   │   ├── config.py           # Settings from env vars
│   │   └── main.py             # FastAPI app, router registration, startup
│   └── requirements.txt
│
└── frontend/
    └── src/
        ├── app/                # Next.js pages (layout, page, login, pricing, admin)
        ├── components/         # ChatAssistant, OccasionPlanner, TryOnModal,
        │                       # WishlistPanel, FindThisLook, TrendAnalyzer,
        │                       # Header, Footer, UserMenu, AuthProvider
        ├── contexts/           # SettingsContext (subscription price)
        ├── lib/api.ts          # All API call functions
        └── middleware.ts       # Auth guard (redirects to /login)
```

---

## Local Setup

### Prerequisites
- Python 3.10, conda
- Node.js 18+
- PostgreSQL (or Neon connection string)
- Google Gemini API key (from [aistudio.google.com](https://aistudio.google.com))
- Serper.dev API key
- Razorpay account (test or live)
- Resend.com API key

### Backend

```bash
cd backend
conda create -n fashion-ai python=3.10
conda activate fashion-ai
pip install -r requirements.txt

# Create backend/.env (see Environment Variables section below)

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install

# Create frontend/.env.local (see Environment Variables section below)

npm run dev
```

App runs at `http://localhost:3000`

---

## Environment Variables

### backend/.env

```env
# Database
DATABASE_URL=postgresql://...

# Google Gemini
GEMINI_API_KEY=AIza...

# Serper.dev (Google Shopping + Lens)
SERPER_API_KEY=...

# JWT
JWT_SECRET=...

# Razorpay
RAZORPAY_KEY_ID=rzp_live_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_PLAN_ID=plan_...
RAZORPAY_WEBHOOK_SECRET=...

# Email
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=you@yourdomain.com

# Admin
ADMIN_EMAILS=your@email.com

# Frontend
FRONTEND_URL=http://localhost:3000
```

### frontend/.env.local

```env
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_RAZORPAY_KEY_ID=rzp_live_...
```

---

## Free vs Premium

| Feature | Free | Premium (₹25/month) |
|---|---|---|
| AI Chat | 15 / day | Unlimited |
| Chat History | — | 30-day retention |
| Wishlist | 20 items | Unlimited |
| Price Drop Alerts | 3 alerts | Unlimited |
| Virtual Try-On | — | Unlimited |
| Occasion Planner | 2 plans / day | Unlimited |
| Outfit Completion | Unlimited | Unlimited |
| Trend Discovery | Unlimited | Unlimited |
| Find This Look | Unlimited | Unlimited |

---

## Key API Endpoints

```
POST /api/v1/chat/                        — AI chat message
POST /api/v1/occasion/categories          — Extract occasion context
POST /api/v1/occasion/plan                — Build full outfit
POST /api/v1/occasion/swap                — Swap one piece
POST /api/v1/tryon/                       — Virtual try-on (premium)
GET  /api/v1/wishlist/                    — Get user wishlist
POST /api/v1/wishlist/                    — Add to wishlist
DELETE /api/v1/wishlist/{product_id}      — Remove from wishlist
POST /api/v1/alerts/register              — Register price alerts
GET  /api/v1/alerts/{email}               — Get tracked alerts
POST /api/v1/payments/checkout            — Create Razorpay subscription
POST /api/v1/payments/verify              — Verify payment + upgrade tier
POST /api/v1/users/sync                   — Create/find user, issue JWT
GET  /api/v1/users/me                     — Get current user profile
GET  /api/v1/settings                     — Public app settings (subscription price)
GET  /api/v1/admin/stats                  — Dashboard stats (admin only)
GET  /api/v1/admin/users                  — Paginated users (admin only)
PATCH /api/v1/admin/settings              — Update subscription price (admin only)
```

---

## License

MIT
