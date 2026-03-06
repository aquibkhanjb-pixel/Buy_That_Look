# How to Add More Products to the Database

This guide covers all the ways to add more fashion products to the system and get them searchable.

---

## Overview — The 3-Step Pipeline

Every method follows the same flow:

```
Scrape / Import Products  →  Generate CLIP Embeddings  →  Search Index Updated
       (DB)                        (FAISS)                    (ready to search)
```

---

## Method 1: Run the Ajio Scraper (Recommended)

The Ajio spider is the most reliable — it uses Ajio's internal JSON API and requires no browser.

### Prerequisites
Make sure the `fashionscraperenv` is activated and the backend `.env` has the correct `DATABASE_URL`.

### Step 1 — Scrape products into the database

Open a terminal in the `scraper/` directory:

```bash
cd scraper

# Activate the scraper environment
fashionscraperenv\Scripts\activate   # Windows
# source fashionscraperenv/bin/activate  # Linux/Mac

# Scrape 500 products across all categories
python run_scraper.py ajio --max-products 500

# Scrape a specific category only
python run_scraper.py ajio --category "women dresses" --max-products 200
python run_scraper.py ajio --category "men jackets" --max-products 200
python run_scraper.py ajio --category "sneakers" --max-products 100
```

**Available categories in the Ajio spider:**

| Category Keyword | Maps To |
|---|---|
| `men t-shirts` | Men > T-Shirts |
| `men shirts` | Men > Shirts |
| `men jeans` | Men > Pants |
| `men jackets` | Men > Jackets |
| `women dresses` | Women > Dresses |
| `women tops` | Women > Tops |
| `women jeans` | Women > Pants |
| `sneakers` | Accessories > Sneakers |
| `handbags` | Accessories > Bags |
| `watches` | Accessories > Watches |
| `kurta men` | Men > Ethnic Wear |
| `sarees` | Women > Ethnic Wear |

### Step 2 — Generate embeddings and update the search index

Open a **new terminal** in the `backend/` directory with the `fashion-ai` conda environment:

```bash
cd backend

# Activate environment
conda activate fashion-ai

# Generate CLIP embeddings for all new (unembedded) products
python -m scripts.embedding_pipeline

# With image download for better visual search accuracy
python -m scripts.embedding_pipeline --download-images

# Limit how many to embed in one run (useful for large batches)
python -m scripts.embedding_pipeline --limit 500
```

### Step 3 — Verify

```bash
# Check how many products and vectors are indexed
curl http://localhost:8000/api/v1/search/stats
```

You should see `total_vectors` increase.

---

## Method 2: Run the Full Pipeline (Scrape + Embed in One Command)

The `scrape_and_index` orchestrator handles everything in one command. Run from `backend/`:

```bash
cd backend
conda activate fashion-ai

# Full pipeline: scrape 200 products, embed, clear cache
python -m scripts.scrape_and_index --spider ajio --max-products 200

# Scrape only (don't embed yet)
python -m scripts.scrape_and_index --spider ajio --max-products 500 --scrape-only

# Embed only (products already in DB but not yet embedded)
python -m scripts.scrape_and_index --embed-only

# Embed without downloading images (faster, uses text embeddings as fallback)
python -m scripts.scrape_and_index --embed-only --no-download
```

---

## Method 3: Run Other Available Spiders

Beyond Ajio, the following spiders are available in `scraper/fashion_scraper/spiders/`:

```bash
cd scraper
fashionscraperenv\Scripts\activate

# Demo spider — uses Fake Store API (good for testing, English products)
python run_scraper.py demo --max-products 100

# Amazon India spider
python run_scraper.py amazon_india --max-products 200

# Flipkart spider
python run_scraper.py flipkart --max-products 200

# Myntra spider
python run_scraper.py myntra --max-products 200
```

> **Note:** Amazon, Flipkart, and Myntra spiders may require additional configuration or may be blocked by the sites. The `ajio` and `demo` spiders are the most stable.

After scraping with any spider, run Step 2 (embedding pipeline) from the backend.

---

## Method 4: Manually Insert Products via the Database

For adding a small number of specific products without scraping:

```bash
cd backend
conda activate fashion-ai

# Open a Python shell
python

>>> from app.core.database import SessionLocal
>>> from app.models.product import Product
>>> import uuid

>>> db = SessionLocal()
>>> product = Product(
...     id=uuid.uuid4(),
...     product_id="CUSTOM_001",
...     source_site="manual",
...     title="Custom Product Name",
...     description="Product description here",
...     brand="Brand Name",
...     price=999.0,
...     original_price=1999.0,
...     currency="INR",
...     category="Women > Dresses",
...     image_url="https://example.com/image.jpg",
...     product_url="https://example.com/product",
...     is_active=True,
... )
>>> db.add(product)
>>> db.commit()
>>> print("Product added!")
>>> db.close()
```

Then run the embedding pipeline to make it searchable:

```bash
python -m scripts.embedding_pipeline
```

---

## Method 5: Rebuild the Full FAISS Index from Scratch

Use this if the index gets out of sync or you want a clean rebuild:

```bash
cd backend
conda activate fashion-ai

python -m scripts.rebuild_index
```

This re-embeds **all** products in the database and rebuilds the index. It takes longer but guarantees consistency.

---

## Quick Reference — Command Cheat Sheet

```bash
# --- SCRAPING (from scraper/ dir, fashionscraperenv activated) ---

# Scrape all Ajio categories, 500 products
python run_scraper.py ajio --max-products 500

# Scrape specific category
python run_scraper.py ajio --category "women dresses" --max-products 200

# Demo spider (for testing)
python run_scraper.py demo --max-products 50


# --- EMBEDDING (from backend/ dir, fashion-ai conda env activated) ---

# Embed all new products
python -m scripts.embedding_pipeline

# Embed with image download
python -m scripts.embedding_pipeline --download-images

# Full pipeline in one command
python -m scripts.scrape_and_index --spider ajio --max-products 200

# Rebuild entire index
python -m scripts.rebuild_index


# --- VERIFY ---
curl http://localhost:8000/api/v1/search/stats
curl http://localhost:8000/api/v1/health
```

---

## Troubleshooting

### Products scraped but not appearing in search
- The scraper saves to DB but embedding pipeline must be run separately.
- Run `python -m scripts.embedding_pipeline` from the `backend/` directory.

### Embedding pipeline says "0 products to process"
- All products in the DB already have embeddings.
- Check if the scraper actually saved new products: `curl http://localhost:8000/api/v1/products/?limit=5`

### Spider returns 0 products
- Ajio's API may have changed. Try running with a different category keyword.
- Try the `demo` spider first to confirm the pipeline works end-to-end.

### DATABASE_URL errors during scraping
- The scraper needs the backend `.env` file's `DATABASE_URL`.
- Make sure `backend/.env` exists and has `DATABASE_URL=sqlite:///./test.db` (for SQLite) or your PostgreSQL URL.

---

## Current Database Info

| Item | Value |
|---|---|
| Total products | 1,544 |
| Indexed vectors | 1,542 |
| Source | Ajio.com |
| DB type | SQLite (`backend/test.db`) |
| FAISS index path | `backend/data/indices/fashion_products.index` |
