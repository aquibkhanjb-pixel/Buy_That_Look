# Fashion Recommendation System — Project Explanation

## Problem Statement

Online fashion shopping is overwhelming. A user might see a jacket on the street, at a party, or on social media and think — "I want something like that." But how do they find it online? They would have to manually browse through thousands of products on different e-commerce websites, trying various keywords, hoping something similar shows up. This is frustrating, time-consuming, and often leads to the user giving up.

Traditional text-based search on e-commerce platforms also has limitations. If a user types "blue floral summer dress," the search engine relies on product titles and tags. If a seller didn't tag their product correctly, it won't appear — even if it's a perfect match visually.

**The core problem**: There is no easy way for a user to search for fashion products using the way they naturally think — by what something *looks like*, not just what it's called.

---

## How Our System Solves It

We built a **multi-modal fashion search engine** that lets users find fashion products in three ways:

1. **Image Search** — Upload a photo of any outfit or fashion item, and the system finds visually similar products from real e-commerce stores.
2. **Text Search** — Describe what you're looking for in plain language (e.g., "black leather handbag"), and the system understands the visual concept behind those words.
3. **Hybrid Search** — Combine both. Upload a photo and add a description like "this dress but in red." The system blends both inputs to find exactly what the user wants.

Every result links directly to the actual product page on the e-commerce site, with real prices in INR, so the user can click and buy immediately.

---

## System Architecture Overview

The system has four main components:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────>│   Backend    │────>│  PostgreSQL   │     │   Scraper    │
│  (Next.js)   │<────│  (FastAPI)   │────>│   Database    │<────│  (Scrapy)    │
│              │     │              │────>│              │     │              │
│  React UI    │     │  CLIP Model  │     │  Products    │     │  Ajio.com    │
│  Tailwind    │     │  FAISS Index │     │  Embeddings  │     │  Flipkart    │
│              │     │  Redis Cache │     │  Search Logs │     │  Myntra      │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
     :3000                :8000                :5432
```

---

## Detailed Workflow

### Step 1: Data Collection (Scraper)

Before users can search, we need products in our database. We built web scrapers using **Scrapy** that collect real fashion products from Indian e-commerce sites like **Ajio**, **Flipkart**, **Myntra**, and **Amazon India**.

For each product, the scraper collects:
- Product title, brand, description
- Price in INR (with original price if discounted)
- Product image URL (from the site's CDN)
- Direct product page URL (so users can click and buy)
- Category (Men > Shirts, Women > Dresses, Accessories > Bags, etc.)

The scraped data goes through a **cleaning pipeline** that:
- Standardizes category names across different sites
- Normalizes prices and currency formats
- Removes duplicates
- Validates required fields

Finally, a **database pipeline** stores everything in PostgreSQL.

Currently, we have **1500+ real products** across 16 categories including clothing, footwear, bags, watches, sunglasses, and ethnic wear.

### Step 2: Generating Embeddings (CLIP + FAISS)

This is the core ML part. We use OpenAI's **CLIP (Contrastive Language-Image Pretraining)** model — specifically the `ViT-B/32` variant — to convert product images into numerical representations called **embeddings**.

**What is CLIP?**
CLIP was trained on 400 million image-text pairs from the internet. It learned to understand the relationship between images and text. It maps both images and text into the same 512-dimensional vector space. So if you have an image of a red dress and the text "red dress," both will map to nearby points in this space.

**How we use it:**
1. For each product in our database, we download its image from the e-commerce site's CDN.
2. We pass the image through CLIP's image encoder, which outputs a 512-dimensional vector (the embedding).
3. We normalize this vector (L2 normalization) so that cosine similarity equals dot product.
4. We store all embeddings in a **FAISS index** (Facebook AI Similarity Search).

**Why FAISS?**
FAISS is a library for efficient similarity search. Instead of comparing a query against every product one by one (which would be slow), FAISS uses optimized data structures to find the most similar vectors in milliseconds, even with millions of products.

We use `IndexFlatIP` (Inner Product) for exact search on our current catalog. For larger catalogs (100k+ products), the system can switch to `IndexHNSWFlat` for approximate but faster search.

### Step 3: User Searches (The Three Modes)

#### Image Search
1. User uploads a photo (JPEG, PNG, or WebP).
2. The backend passes the image through CLIP's image encoder → 512-dim embedding.
3. This embedding is compared against all product embeddings in FAISS using cosine similarity.
4. Products with similarity above 85% are returned, ranked by similarity score.
5. The frontend displays the results with product images, prices, and direct buy links.

**Why 85% threshold?** Since both the query and the indexed products are in the same visual space (image-to-image), the similarity scores are naturally high. Setting 85% ensures only truly visually similar products are shown.

#### Text Search
1. User types a description like "black leather handbag."
2. The backend passes the text through CLIP's text encoder → 512-dim embedding.
3. This text embedding is compared against the image embeddings in FAISS.
4. Products with raw similarity above 18% are returned (CLIP cross-modal scores are lower than image-to-image).
5. The raw scores are **normalized** to a user-friendly display range (55%–95%) since text-to-image matching in CLIP inherently produces lower numbers than image-to-image.

**Why normalization?** CLIP's text-to-image similarity typically ranges from 0.18 to 0.38. Showing "32% match" to a user would feel wrong even though it's actually a great match. We linearly scale these to a range that makes sense to the user.

#### Hybrid Search
1. User uploads a photo AND types a description (e.g., photo of a blue jacket + "but in black").
2. Both are encoded separately through CLIP.
3. The embeddings are combined: `hybrid = alpha × image_embedding + (1-alpha) × text_embedding`
4. The `alpha` parameter (0 to 1) controls the weight — the user can slide between "more like the image" and "more like the text."
5. The hybrid embedding is searched against FAISS and results are normalized for display.

### Step 4: Result Delivery

Search results are returned to the frontend as JSON containing:
- Product title, brand, category
- Price in INR (with original price for discounts)
- Product image URL (loaded directly from the e-commerce CDN)
- **Direct product URL** — clicking takes the user to the actual product page to buy
- Similarity percentage

The frontend displays these in a responsive grid with match percentages shown as badges.

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Frontend** | Next.js 14, React, Tailwind CSS | Fast SSR, component-based UI, utility-first styling |
| **Backend** | FastAPI (Python) | Async support, automatic API docs, Pydantic validation |
| **ML Model** | CLIP ViT-B/32 (OpenAI) | Multi-modal (understands both images and text in same space) |
| **Vector Search** | FAISS (Facebook) | Millisecond similarity search over thousands of vectors |
| **Database** | PostgreSQL | Reliable relational DB for product metadata |
| **Cache** | Redis | Caches search results and text embeddings for faster repeated queries |
| **Scraper** | Scrapy + Playwright | Scrapy for structured crawling, Playwright for JS-rendered sites |
| **Deployment** | Docker Compose | 5 containerized services (frontend, backend, postgres, redis, scraper) |

---

## Key Design Decisions

### 1. Image Embeddings Only (No Mixed Embeddings)
We store only image embeddings in the FAISS index. Early experiments showed that mixing text and image embeddings in the same index causes text-embedded products to dominate all text searches — because text-to-text similarity (0.6–0.9) is much higher than text-to-image similarity (0.2–0.35). Keeping the index pure image-only and handling text search through CLIP's cross-modal capability gives consistent results.

### 2. Per-Mode Similarity Thresholds
Different search modes need different thresholds because CLIP produces different score ranges:
- **Image search**: 85% — same visual space, high scores
- **Hybrid search**: 35% raw (displayed as 60–100%) — blended embedding
- **Text search**: 18% raw (displayed as 55–95%) — cross-modal gap

### 3. Score Normalization for Display
Raw CLIP scores are mathematically correct but confusing for users. A text search score of 0.31 is actually excellent, but showing "31% match" would make users think the result is bad. We normalize each mode's scores to intuitive percentage ranges.

### 4. Listing-Page-Only Scraping
We scrape search/listing pages only (not individual product pages). One listing page gives 40–50 products worth of data. This means fewer requests, lower risk of getting blocked, and faster data collection. The product URLs still link to the real product pages.

### 5. Singleton Pattern for ML Services
Both the CLIP service and FAISS search engine use the singleton pattern. The CLIP model takes ~3 seconds to load and uses ~700MB of memory. Loading it once and sharing across all requests is essential for performance.

---

## Database Schema

```
products                    embeddings               search_logs
├── id (UUID, PK)          ├── id (INT, PK)         ├── id (INT, PK)
├── product_id (unique)    ├── product_id (FK)      ├── query_type
├── source_site            ├── embedding_type       ├── query_text
├── title                  ├── model_version        ├── query_image_hash
├── description            ├── vector_index         ├── filters_applied
├── brand                  └── created_at           ├── results_count
├── price                                           ├── top_result_ids
├── original_price         categories               ├── latency_ms
├── currency               ├── id (INT, PK)         └── created_at
├── category               ├── name
├── color                  ├── parent_id (FK)
├── image_url              ├── level
├── product_url            └── path
├── is_active
└── created_at
```

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /api/v1/search/image` | POST | Search by uploaded image |
| `POST /api/v1/search/text` | POST | Search by text description |
| `POST /api/v1/search/hybrid` | POST | Combined image + text search |
| `GET /api/v1/products/` | GET | List products with filters & pagination |
| `GET /api/v1/products/{id}` | GET | Get single product details |
| `GET /api/v1/products/{id}/similar` | GET | Find similar products |
| `GET /api/v1/search/stats` | GET | Search engine & cache statistics |
| `GET /api/v1/health` | GET | Health check |

All search endpoints are **rate-limited** (10 requests/minute for image/hybrid, 30 for text) using SlowAPI.

---

## Performance Characteristics

- **Search latency**: ~50–100ms for a fresh search (CLIP encoding + FAISS search)
- **Cached search**: ~2ms (Redis-cached results)
- **Index size**: 1542 products × 512 dimensions × 4 bytes = ~3MB
- **CLIP model**: ~340MB on disk, ~700MB in memory
- **Scraping speed**: ~45 products per API call, 500+ products per minute

---

## Challenges Faced & How I Solved Them

### 1. Cross-Modal Similarity Gap
CLIP's text-to-image similarity scores (0.18–0.38) are much lower than image-to-image (0.70–0.95). A single threshold doesn't work for both. **Solution**: Separate thresholds per search mode with display-score normalization.

### 2. Text Embedding Contamination
When some products had text embeddings (because their images failed to download) mixed with image embeddings in FAISS, those few products dominated every text search. **Solution**: Use image-only embeddings in the index. Skip products without downloadable images.

### 3. Anti-Bot Protection on E-Commerce Sites
Myntra blocked with HTTP2 protocol errors, Flipkart returned 403s. **Solution**: Used Ajio's search API (returns JSON directly), added Playwright for JS-rendered sites, implemented respectful rate limiting and retry logic.

### 4. Stale Cache After Index Rebuild
After rebuilding the FAISS index, Redis still served old cached search results. **Solution**: Flush Redis cache after every index rebuild. Simplified the text search endpoint to always use `search_by_text()` instead of having separate cached/uncached code paths.

---

## Future Improvements

1. **More e-commerce sources** — Add working scrapers for Myntra, Amazon India with proxy rotation
2. **Dual-index strategy** — Separate FAISS indices for image and text embeddings to improve text search accuracy
3. **User feedback loop** — Use click-through data from search_logs to fine-tune ranking
4. **Personalized recommendations** — Track user preferences and adjust results
5. **Real-time price updates** — Periodic re-scraping to keep prices current
6. **GPU acceleration** — Move CLIP inference to GPU for 10x faster encoding


fashionscraperenv for frontend
fashion_scraper for backend