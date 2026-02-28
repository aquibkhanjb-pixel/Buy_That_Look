"""
Scrape-and-Index Orchestrator - Full data pipeline automation.

Orchestrates the complete flow:
1. Run web scraper to fetch new products
2. Generate CLIP embeddings for new products
3. Update FAISS index
4. Clear stale cache entries

Can be triggered manually or scheduled via cron/systemd timer.

Usage:
    # Full pipeline: scrape demo + embed + index
    python -m scripts.scrape_and_index

    # Scrape only (skip embedding)
    python -m scripts.scrape_and_index --scrape-only

    # Embed only (skip scraping, process existing unembedded products)
    python -m scripts.scrape_and_index --embed-only

    # With custom scraper args
    python -m scripts.scrape_and_index --spider demo --max-products 100

Cron example (daily at 2 AM):
    0 2 * * * cd /app && python -m scripts.scrape_and_index >> /app/logs/pipeline.log 2>&1
"""

import os
import sys
import subprocess
import argparse
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.core.logging import logger

settings = get_settings()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRAPER_DIR = PROJECT_ROOT / "scraper"
BACKEND_DIR = PROJECT_ROOT / "backend"


def find_scraper_python() -> str:
    """
    Find the Python executable for the scraper environment.

    Checks (in order):
    1. Scraper's own virtualenv (scraper/fashionscraperenv/)
    2. SCRAPER_PYTHON environment variable
    3. Falls back to current Python (sys.executable)
    """
    # Check for scraper's virtualenv
    venv_candidates = [
        SCRAPER_DIR / "fashionscraperenv" / "Scripts" / "python.exe",  # Windows
        SCRAPER_DIR / "fashionscraperenv" / "bin" / "python",          # Linux/Mac
        SCRAPER_DIR / "venv" / "Scripts" / "python.exe",               # Windows alt
        SCRAPER_DIR / "venv" / "bin" / "python",                       # Linux/Mac alt
        SCRAPER_DIR / ".venv" / "Scripts" / "python.exe",              # Windows alt
        SCRAPER_DIR / ".venv" / "bin" / "python",                      # Linux/Mac alt
    ]

    for candidate in venv_candidates:
        if candidate.exists():
            return str(candidate)

    # Check environment variable
    env_python = os.environ.get("SCRAPER_PYTHON")
    if env_python and Path(env_python).exists():
        return env_python

    # Fall back to current Python
    return sys.executable


def run_scraper(
    spider: str = "demo",
    max_products: int = 50,
    category: str = None,
) -> bool:
    """
    Run the Scrapy spider to fetch new products.

    Args:
        spider: Spider name ('demo' or 'generic')
        max_products: Maximum products to scrape
        category: Optional category filter

    Returns:
        True if scraping completed successfully
    """
    print(f"\n{'-'*50}")
    print(f"STAGE 1: Running {spider} scraper")
    print(f"{'-'*50}")

    scraper_python = find_scraper_python()
    print(f"  Using Python: {scraper_python}")

    cmd = [
        scraper_python, "run_scraper.py",
        spider,
        "--max-products", str(max_products),
    ]

    if category:
        cmd.extend(["--category", category])

    try:
        result = subprocess.run(
            cmd,
            cwd=str(SCRAPER_DIR),
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            env={**os.environ, "DATABASE_URL": settings.database_url},
        )

        if result.returncode == 0:
            print(f"  Scraping completed successfully")
            if result.stdout:
                # Print last few lines of output
                lines = result.stdout.strip().split("\n")
                for line in lines[-5:]:
                    print(f"  {line}")
            return True
        else:
            print(f"  Scraping failed (exit code: {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-5:]:
                    print(f"  ERROR: {line}")
            return False

    except subprocess.TimeoutExpired:
        print("  Scraping timed out after 10 minutes")
        return False
    except FileNotFoundError:
        print(f"  Scraper not found at {SCRAPER_DIR}")
        return False
    except Exception as e:
        print(f"  Scraping error: {e}")
        return False


def run_embedding_pipeline(
    batch_size: int = 32,
    limit: int = 0,
    download_images: bool = True,
) -> bool:
    """
    Run the embedding pipeline to process new products.

    Args:
        batch_size: CLIP inference batch size
        limit: Max products to embed (0 = all)
        download_images: Whether to download product images

    Returns:
        True if embedding completed successfully
    """
    print(f"\n{'-'*50}")
    print("STAGE 2: Running embedding pipeline")
    print(f"{'-'*50}")

    try:
        from scripts.embedding_pipeline import run_pipeline
        run_pipeline(
            batch_size=batch_size,
            limit=limit,
            download_images=download_images,
            save_index=True,
        )
        return True

    except Exception as e:
        print(f"  Embedding pipeline error: {e}")
        logger.error(f"Embedding pipeline failed: {e}")
        return False


def clear_cache() -> bool:
    """Clear Redis cache after data update."""
    print(f"\n{'-'*50}")
    print("STAGE 3: Clearing stale cache")
    print(f"{'-'*50}")

    try:
        from app.services.cache_service import cache_service

        if cache_service.connect():
            cache_service.clear_all()
            print("  Cache cleared successfully")
            return True
        else:
            print("  Redis not available - skipping cache clear")
            return True  # Not a failure

    except Exception as e:
        print(f"  Cache clear error: {e}")
        return True  # Non-critical


def run_full_pipeline(
    spider: str = "demo",
    max_products: int = 50,
    category: str = None,
    batch_size: int = 32,
    embed_limit: int = 0,
    download_images: bool = True,
    scrape_only: bool = False,
    embed_only: bool = False,
):
    """
    Run the complete scrape-embed-index pipeline.

    Args:
        spider: Spider name
        max_products: Max products to scrape
        category: Category filter for scraper
        batch_size: Embedding batch size
        embed_limit: Max products to embed
        download_images: Download images for embedding
        scrape_only: Only run scraper, skip embedding
        embed_only: Only run embedding, skip scraper
    """
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'='*60}")
    print(f"Fashion Recommendation - Data Pipeline")
    print(f"Started: {timestamp}")
    print(f"{'='*60}")

    results = {
        "scraper": None,
        "embedding": None,
        "cache": None,
    }

    # Stage 1: Scrape
    if not embed_only:
        results["scraper"] = run_scraper(spider, max_products, category)
        if not results["scraper"] and not embed_only:
            print("\n  WARNING: Scraping failed, continuing with embedding...")

    # Stage 2: Embed
    if not scrape_only:
        results["embedding"] = run_embedding_pipeline(
            batch_size=batch_size,
            limit=embed_limit,
            download_images=download_images,
        )

    # Stage 3: Clear cache
    if not scrape_only:
        results["cache"] = clear_cache()

    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Pipeline Summary")
    print(f"{'='*60}")
    print(f"  Duration: {elapsed:.1f}s")
    print(f"  Scraper:   {'PASS' if results['scraper'] else 'SKIP' if results['scraper'] is None else 'FAIL'}")
    print(f"  Embedding: {'PASS' if results['embedding'] else 'SKIP' if results['embedding'] is None else 'FAIL'}")
    print(f"  Cache:     {'PASS' if results['cache'] else 'SKIP' if results['cache'] is None else 'FAIL'}")

    all_passed = all(v is None or v is True for v in results.values())
    print(f"  Overall:   {'SUCCESS' if all_passed else 'PARTIAL FAILURE'}")
    print(f"{'='*60}\n")

    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Fashion Recommendation Data Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline with demo scraper
  python -m scripts.scrape_and_index

  # Scrape 200 products then embed
  python -m scripts.scrape_and_index --spider demo --max-products 200

  # Only embed products already in DB
  python -m scripts.scrape_and_index --embed-only

  # Only scrape, don't embed yet
  python -m scripts.scrape_and_index --scrape-only

  # Embed without downloading images (use text fallback)
  python -m scripts.scrape_and_index --embed-only --no-download
        """
    )

    parser.add_argument("--spider", default="demo", choices=["demo", "generic"],
                        help="Spider to run (default: demo)")
    parser.add_argument("--max-products", type=int, default=50,
                        help="Max products to scrape (default: 50)")
    parser.add_argument("--category", help="Category filter for scraper")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Embedding batch size (default: 32)")
    parser.add_argument("--embed-limit", type=int, default=0,
                        help="Max products to embed (0 = all)")
    parser.add_argument("--no-download", action="store_true",
                        help="Don't download images (use text embeddings)")
    parser.add_argument("--scrape-only", action="store_true",
                        help="Only run scraper, skip embedding")
    parser.add_argument("--embed-only", action="store_true",
                        help="Only run embedding, skip scraper")

    args = parser.parse_args()

    if args.scrape_only and args.embed_only:
        parser.error("Cannot use --scrape-only and --embed-only together")

    success = run_full_pipeline(
        spider=args.spider,
        max_products=args.max_products,
        category=args.category,
        batch_size=args.batch_size,
        embed_limit=args.embed_limit,
        download_images=not args.no_download,
        scrape_only=args.scrape_only,
        embed_only=args.embed_only,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
