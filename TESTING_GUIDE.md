# Fashion Recommendation System - Testing Guide

Complete guide to set up, install, and verify every feature of the project.

---

## 1. Environment Setup

### 1.1 Create Conda Environment (already done)

```bash
conda create -n fashion-ai python=3.10 -y
conda activate fashion-ai
```

### 1.2 Install Dependencies (correct order)

The key is: **torch first**, then **downgrade setuptools** to install CLIP, then **restore setuptools** and install the rest.

```bash
cd backend

# Step 1: Install PyTorch (CPU version — smaller, faster install)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Step 2: Downgrade setuptools (CLIP needs pkg_resources, removed in setuptools 72+)
pip install "setuptools<70"

# Step 3: Install CLIP (must come AFTER torch, needs old setuptools)
pip install git+https://github.com/openai/CLIP.git --no-build-isolation

# Step 4: Restore setuptools to latest
pip install --upgrade setuptools

# Step 5: Install everything else
pip install -r requirements.txt
```

> **Why these steps?**
> - CLIP's setup.py imports `torch` during build — torch must be installed first.
> - CLIP's setup.py also imports `pkg_resources` which was removed in setuptools v72+.
> - `--no-build-isolation` prevents pip from creating a clean build env without torch.
> - After CLIP is installed, we restore setuptools so other packages work normally.

### 1.3 Verify Installation

```bash
python -c "import clip; print('CLIP OK')"
python -c "import torch; print(f'PyTorch {torch.__version__} OK')"
python -c "import faiss; print('FAISS OK')"
python -c "import fastapi; print('FastAPI OK')"
python -c "from app.config import get_settings; print('Config OK')"
```

All 5 should print "OK". If any fail, re-run the relevant install step.

---

## 2. Database Setup

### Option A: Local PostgreSQL (if PostgreSQL is already installed on your machine)

If you already have PostgreSQL installed locally, create the user and database:

```bash
# Connect to PostgreSQL as superuser (use your postgres password)
psql -U postgres -h 127.0.0.1

# Inside psql, run:
CREATE USER fashionuser WITH PASSWORD 'fashionpass';
CREATE DATABASE fashiondb OWNER fashionuser;
GRANT ALL PRIVILEGES ON DATABASE fashiondb TO fashionuser;
GRANT ALL ON SCHEMA public TO fashionuser;
\q
```

Then start Redis via Docker:

```bash
docker run -d --name fashion_redis \
  -p 6379:6379 \
  redis:7-alpine
```

> **Important:** If you have local PostgreSQL AND Docker PostgreSQL both running on port 5432,
> they will conflict. Stop one of them. To check: `netstat -ano | findstr 5432`

### Option B: Docker (if you don't have local PostgreSQL)

```bash
# From project root
docker run -d --name fashion_postgres \
  -e POSTGRES_USER=fashionuser \
  -e POSTGRES_PASSWORD=fashionpass \
  -e POSTGRES_DB=fashiondb \
  -p 5432:5432 \
  postgres:15-alpine

docker run -d --name fashion_redis \
  -p 6379:6379 \
  redis:7-alpine
```

### Option C: Full Docker Compose

```bash
# From project root
cp .env.example .env
docker-compose up -d postgres redis
```

### 2.1 Create Backend .env File

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` — update DATABASE_URL if needed:

```env
DATABASE_URL=postgresql://fashionuser:fashionpass@localhost:5432/fashiondb
REDIS_URL=redis://localhost:6379
DEBUG=true
```

### 2.2 Create Database Tables

```bash
cd backend
python -c "
from app.core.database import Base, engine
from app.models.product import Product
from app.models.embedding import Embedding
from app.models.category import Category
from app.models.search_log import SearchLog
Base.metadata.create_all(bind=engine)
print('All tables created!')
"
```

### 2.3 Verify Database Connection

```bash
python -c "
from sqlalchemy import create_engine, text
engine = create_engine('postgresql://fashionuser:fashionpass@localhost:5432/fashiondb')
with engine.connect() as conn:
    print(conn.execute(text('SELECT 1')).scalar())
    print('DB OK')
"
```

---

## 3. Run Automated Tests (no DB required)

Tests use SQLite in-memory and mocked services — no PostgreSQL/Redis needed.

```bash
cd backend

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_services.py
pytest tests/test_api.py
pytest tests/test_schemas.py

# Run a specific test class
pytest tests/test_services.py::TestSearchEngine

# Run a single test
pytest tests/test_services.py::TestSearchEngine::test_search_returns_results
```

### Expected Output

```
tests/test_services.py   - ~38 tests PASSED
tests/test_api.py        - ~30 tests PASSED
tests/test_schemas.py    - ~25 tests PASSED
```

---

## 4. Manual Feature Testing

### 4.1 Start the Backend Server

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see in the console:

```
INFO: Loading CLIP model...
INFO: CLIP model loaded (dim: 512)
INFO: No existing FAISS index found - creating empty index
INFO: Application startup complete
```

### 4.2 Verify API Docs

Open in browser: **http://localhost:8000/docs**

You should see the Swagger UI with all endpoints listed.

---

### 4.3 Test Health Endpoints

```bash
# Basic health
curl http://localhost:8000/api/v1/health
# Expected: {"status":"healthy","service":"Fashion Recommendation API","version":"0.1.0"}

# Liveness
curl http://localhost:8000/api/v1/health/live
# Expected: {"status":"alive"}

# Readiness (checks DB, Redis, CLIP, FAISS)
curl http://localhost:8000/api/v1/health/ready
# Expected: {"status":"not_ready","checks":{"database":true,"redis":true/false,"clip_model":true,"faiss_index":false}}
# Note: faiss_index is false because we haven't loaded any data yet

# ML status
curl http://localhost:8000/api/v1/health/ml
# Expected: Shows CLIP model info, FAISS stats, cache stats
```

---

### 4.4 Generate Sample Data & Build Index

```bash
cd backend

# Generate 50 sample products with placeholder images
python -m scripts.generate_sample_data --num-products 50

# You should see:
# Generating 50 sample products...
# Loading CLIP model...
# Building FAISS index with 50 vectors...
# Index saved to ./data/indices/fashion_products.index
# Testing search with sample query...
# Found X results for 'red dress'
```

Now restart the server (or it will auto-reload if using `--reload`).

Verify the index loaded:

```bash
curl http://localhost:8000/api/v1/health/ready
# faiss_index should now be true, total_vectors: 50
```

---

### 4.5 Test Text Search

```bash
# Basic text search
curl -X POST http://localhost:8000/api/v1/search/text \
  -H "Content-Type: application/json" \
  -d '{"query": "red summer dress", "k": 5}'

# Expected: JSON with query_id, results array (5 items), latency_ms, total_results
# Each result has: title, price, category, similarity score, image_url, product_url

# Text search with filters
curl -X POST http://localhost:8000/api/v1/search/text \
  -H "Content-Type: application/json" \
  -d '{"query": "blue jacket", "k": 10, "filters": {"min_price": 20, "max_price": 150, "category": "Men"}}'

# Expected: Only results matching the filters
```

**What to verify:**
- [ ] Response contains `query_id` (UUID)
- [ ] `results` is an array of product objects
- [ ] Each result has `similarity` score between 0-1
- [ ] `latency_ms` is reasonable (<1000ms first call, faster after)
- [ ] Filters are applied correctly (check returned prices/categories)

---

### 4.6 Test Image Search

```bash
# Search with an image (use any JPEG/PNG file)
curl -X POST http://localhost:8000/api/v1/search/image \
  -F "image=@/path/to/any/image.jpg" \
  -F "k=5"

# On Windows PowerShell:
curl.exe -X POST http://localhost:8000/api/v1/search/image `
  -F "image=@C:\path\to\image.jpg" `
  -F "k=5"

# With filters
curl -X POST "http://localhost:8000/api/v1/search/image?k=5&min_price=20&category=Women" \
  -F "image=@/path/to/image.jpg"
```

> **Tip:** You can also test this from the Swagger UI at http://localhost:8000/docs
> — click on POST `/api/v1/search/image`, click "Try it out", upload a file.

**What to verify:**
- [ ] Accepts JPEG, PNG, WebP files
- [ ] Rejects non-image files (should return 400)
- [ ] Returns results sorted by similarity
- [ ] Rejects files over 10MB

---

### 4.7 Test Hybrid Search

```bash
curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -F "image=@/path/to/image.jpg" \
  -F "query=similar but in blue" \
  -F "alpha=0.5" \
  -F "k=10"
```

**What to verify:**
- [ ] Requires BOTH image and text query
- [ ] Alpha=1.0 gives image-only results
- [ ] Alpha=0.0 gives text-only results
- [ ] Alpha=0.5 blends both modalities

---

### 4.8 Test Search Stats

```bash
curl http://localhost:8000/api/v1/search/stats

# Expected: search_engine stats (total_vectors, index_type) + cache stats
```

---

### 4.9 Test Product Endpoints

```bash
# List all products
curl "http://localhost:8000/api/v1/products/?page=1&page_size=5"

# Expected: paginated list with items, total, page, has_more

# List with filters
curl "http://localhost:8000/api/v1/products/?category=Women&min_price=30&max_price=100"
```

> **Note:** Product detail (`/products/{id}`) and similar products
> (`/products/{id}/similar`) require a real product UUID from the database.
> Use the `id` from a search result or product list response.

---

### 4.10 Test Rate Limiting

```bash
# Send 11 rapid image search requests — the 11th should be rate-limited
for i in $(seq 1 11); do
  echo "Request $i:"
  curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/search/text \
    -H "Content-Type: application/json" \
    -d '{"query": "test query number '$i'"}'
  echo ""
done

# First 30 should return 200, then you'll get 429 (Too Many Requests)
# Text search limit: 30/minute, Image/Hybrid: 10/minute
```

---

### 4.11 Test Redis Caching

```bash
# First request (cache miss — generates embedding)
time curl -X POST http://localhost:8000/api/v1/search/text \
  -H "Content-Type: application/json" \
  -d '{"query": "elegant black evening dress", "k": 5}'

# Second identical request (cache hit — much faster)
time curl -X POST http://localhost:8000/api/v1/search/text \
  -H "Content-Type: application/json" \
  -d '{"query": "elegant black evening dress", "k": 5}'

# The second request should be noticeably faster
# Check cache stats:
curl http://localhost:8000/api/v1/search/stats
# Look for "hits" and "misses" counts
```

---

### 4.12 Test Search Logging

After running some searches, check the database:

```bash
# Connect to PostgreSQL
docker exec -it fashion_postgres psql -U fashionuser -d fashiondb

# View search logs
SELECT id, query_type, query_text, results_count, latency_ms, created_at
FROM search_logs
ORDER BY created_at DESC
LIMIT 10;

# Count searches by type
SELECT query_type, COUNT(*) as count
FROM search_logs
GROUP BY query_type;

# Exit
\q
```

---

## 5. Test the Data Pipeline

### 5.1 Run the Scraper (Demo)

```bash
cd scraper
pip install -r requirements.txt
python run_scraper.py demo --max-products 20

# Expected: Scrapes products from Fake Store API, saves to DB
```

### 5.2 Run the Embedding Pipeline

```bash
cd backend

# Embed all products that don't have embeddings yet
python -m scripts.embedding_pipeline --limit 20

# Expected output:
# Step 1: Fetching products without embeddings... Found X products
# Step 2: Loading CLIP model...
# Step 4: Generating embeddings...
# Step 5: Adding embeddings to FAISS index...
# Step 7: Saving FAISS index to disk...
# Pipeline complete!
```

### 5.3 Run the Full Pipeline (Scrape + Embed)

```bash
cd backend

# Full pipeline: scrape -> embed -> cache clear
python -m scripts.scrape_and_index --spider demo --max-products 20

# Embed-only mode (process products already in DB)
python -m scripts.scrape_and_index --embed-only

# Scrape-only mode (no embedding)
python -m scripts.scrape_and_index --scrape-only
```

### 5.4 Rebuild Index from Scratch

```bash
cd backend

# Full rebuild (re-generates all embeddings)
python -m scripts.rebuild_index --text-only

# With HNSW index (for large catalogs)
python -m scripts.rebuild_index --hnsw --text-only
```

---

## 6. Test the Frontend

### 6.1 Install & Run

```bash
cd frontend

npm install
cp .env.example .env

# Make sure .env has the correct backend URL:
# NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev
```

Open **http://localhost:3000** in your browser.

### 6.2 Frontend Feature Checklist

| Feature | How to Test | Expected |
|---------|------------|----------|
| **Header** | Load page | Logo + "Fashion Finder" title visible |
| **Search Tabs** | Click tabs | Switches between Image/Text/Hybrid |
| **Text Search** | Type "red dress" and submit | Results grid appears with product cards |
| **Example Queries** | Click an example chip | Auto-fills search and runs query |
| **Image Search** | Drag-drop or click to upload image | Preview shown, results appear after search |
| **Hybrid Search** | Upload image + type text + adjust slider | Combined results appear |
| **Alpha Slider** | Drag slider left/right | Results change (text-heavy vs image-heavy) |
| **Results Grid** | Perform any search | Cards show image, title, price, similarity % |
| **Filters** | Set price range, category, brand | Results filtered accordingly |
| **Clear Filters** | Click "Clear" button | Filters reset |
| **Product Modal** | Click a product card | Modal with details, larger image, buy link |
| **Responsive** | Resize browser window | Layout adapts (4 cols -> 2 cols -> 1 col) |

---

## 7. Test with Docker Compose (Full Stack)

```bash
# From project root
cp .env.example .env
docker-compose up -d

# Wait ~60s for backend to load CLIP model
# Check logs:
docker-compose logs -f backend

# When you see "Application startup complete":
# Frontend:  http://localhost:3000
# API Docs:  http://localhost:8000/docs
# PostgreSQL: localhost:5432
# Redis:      localhost:6379

# Run scraper on-demand:
docker-compose --profile scraper run scraper

# Stop everything:
docker-compose down

# Stop and remove data volumes:
docker-compose down -v
```

---

## 8. Quick Verification Checklist

Run through this checklist to confirm everything works:

### Backend
- [ ] `pytest` — all tests pass
- [ ] Server starts without errors
- [ ] CLIP model loads successfully
- [ ] `/api/v1/health` returns healthy
- [ ] `/docs` shows Swagger UI

### Search (after generating sample data)
- [ ] Text search returns results
- [ ] Image search accepts upload and returns results
- [ ] Hybrid search works with image + text
- [ ] Filters work (price, category, brand)
- [ ] Rate limiting kicks in after threshold
- [ ] Cache speeds up repeated queries

### Data Pipeline
- [ ] Sample data generator creates products + index
- [ ] Scraper fetches products from demo API
- [ ] Embedding pipeline processes new products
- [ ] Index rebuild completes without errors

### Frontend
- [ ] Page loads at localhost:3000
- [ ] All 3 search modes work
- [ ] Results grid displays product cards
- [ ] Product modal opens on click

### Docker
- [ ] `docker-compose up -d` starts all services
- [ ] All health checks pass
- [ ] Frontend can reach backend API

---

## 9. Troubleshooting

### CLIP Install Fails
```bash
# Make sure torch is installed FIRST
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install git+https://github.com/openai/CLIP.git --no-build-isolation
```

### Database Connection Error
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Test connection
python -c "
from sqlalchemy import create_engine, text
engine = create_engine('postgresql://fashionuser:fashionpass@localhost:5432/fashiondb')
with engine.connect() as conn:
    print(conn.execute(text('SELECT 1')).scalar())
    print('DB OK')
"
```

### Redis Connection Error
```bash
# Check Redis is running
docker ps | grep redis

# Test connection
python -c "
import redis
r = redis.from_url('redis://localhost:6379')
r.ping()
print('Redis OK')
"
```

### FAISS Index Not Found
```bash
cd backend
python -m scripts.generate_sample_data --num-products 50
# This creates the index at data/indices/fashion_products.index
```

### Frontend Can't Reach Backend
```bash
# Check backend is running
curl http://localhost:8000/api/v1/health

# Check CORS — backend must allow frontend origin
# Verify CORS_ORIGINS in backend/.env includes http://localhost:3000
```

### Port Already in Use
```bash
# Find and kill process on port 8000
# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Or use different ports:
uvicorn app.main:app --port 8001
```
