"""
Embedding Pipeline - Generates CLIP embeddings for products in the database.

Reads products from PostgreSQL that don't yet have embeddings,
downloads/loads their images, generates CLIP embeddings, and
updates the FAISS index incrementally.

Usage:
    # Process all products without embeddings
    python -m scripts.embedding_pipeline

    # Process with batch size and real image download
    python -m scripts.embedding_pipeline --batch-size 64 --download-images

    # Limit to specific number of products
    python -m scripts.embedding_pipeline --limit 100
"""

import os
import sys
import json
import uuid
import argparse
from pathlib import Path
from io import BytesIO
from datetime import datetime

import numpy as np
import requests
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.core.logging import logger
from app.services.clip_service import clip_service
from app.services.search_engine import search_engine

settings = get_settings()


def get_db_session():
    """Create a database session."""
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session(), engine


def fetch_products_without_embeddings(session, limit: int = 0) -> list:
    """
    Fetch products from the database that don't have embeddings yet.

    Args:
        session: SQLAlchemy session
        limit: Max products to fetch (0 = all)

    Returns:
        List of product dicts
    """
    query = text("""
        SELECT p.id, p.product_id, p.title, p.description, p.brand,
               p.price, p.original_price, p.currency, p.category,
               p.subcategory, p.color, p.image_url, p.additional_images,
               p.product_url, p.source_site
        FROM products p
        LEFT JOIN embeddings e ON p.id = e.product_id
        WHERE e.id IS NULL AND p.is_active = TRUE
        ORDER BY p.created_at DESC
    """)

    if limit > 0:
        query = text(str(query) + f" LIMIT {limit}")

    result = session.execute(query)
    columns = result.keys()
    products = [dict(zip(columns, row)) for row in result.fetchall()]

    return products


def download_image(url: str, timeout: int = 15) -> bytes:
    """Download image from URL."""
    try:
        response = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        })
        response.raise_for_status()

        # Verify it's actually an image
        img = Image.open(BytesIO(response.content))
        img.verify()

        return response.content
    except Exception as e:
        logger.warning(f"Failed to download image from {url[:80]}: {e}")
        return None


def load_local_image(image_path: str) -> bytes:
    """Load image from local storage."""
    full_path = Path(settings.image_storage_path) / image_path
    if full_path.exists():
        return full_path.read_bytes()
    return None


def get_image_bytes(product: dict) -> bytes:
    """
    Get image bytes for a product, trying local storage first, then URL.

    Args:
        product: Product dict with image_url field

    Returns:
        Image bytes or None
    """
    image_url = product.get("image_url", "")

    # Try local path first (from scraper downloads)
    local_path = Path(settings.image_storage_path) / product.get("source_site", "") / product.get("product_id", "")
    if local_path.exists():
        for img_file in local_path.glob("*"):
            if img_file.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                try:
                    return img_file.read_bytes()
                except Exception:
                    continue

    # Fall back to downloading from URL
    if image_url and image_url.startswith("http"):
        return download_image(image_url)

    return None


def generate_embeddings_batch(
    products: list,
    batch_size: int = 32,
    download_images: bool = True,
) -> tuple:
    """
    Generate CLIP embeddings for a batch of products.

    Args:
        products: List of product dicts
        batch_size: Processing batch size
        download_images: Whether to download images from URLs

    Returns:
        Tuple of (embeddings array, successful product list, failed product IDs)
    """
    if not clip_service.is_loaded():
        if not clip_service.load_model():
            raise RuntimeError("Failed to load CLIP model")

    all_embeddings = []
    successful_products = []
    failed_ids = []

    total = len(products)

    for i in range(0, total, batch_size):
        batch = products[i:i + batch_size]
        batch_images = []
        batch_products = []

        for product in batch:
            if download_images:
                image_bytes = get_image_bytes(product)
            else:
                image_bytes = None

            if image_bytes is not None:
                batch_images.append(image_bytes)
                batch_products.append(product)
            else:
                # Try text-based embedding as fallback
                title = product.get("title", "")
                description = product.get("description", "")
                text_query = f"{title}. {description}" if description else title

                embedding = clip_service.encode_text(text_query)
                if embedding is not None:
                    all_embeddings.append(embedding)
                    successful_products.append(product)
                else:
                    failed_ids.append(str(product.get("id", "unknown")))
                    logger.warning(f"Failed to process: {product.get('product_id')}")

        # Process image batch
        if batch_images:
            embeddings = clip_service.encode_images_batch(batch_images, batch_size=batch_size)
            if embeddings is not None:
                all_embeddings.extend(embeddings)
                successful_products.extend(batch_products)
            else:
                # Fall back to individual processing
                for img_bytes, prod in zip(batch_images, batch_products):
                    embedding = clip_service.encode_image(img_bytes)
                    if embedding is not None:
                        all_embeddings.append(embedding)
                        successful_products.append(prod)
                    else:
                        failed_ids.append(str(prod.get("id", "unknown")))

        processed = min(i + batch_size, total)
        logger.info(f"Progress: {processed}/{total} products processed")

    if all_embeddings:
        return np.array(all_embeddings, dtype=np.float32), successful_products, failed_ids
    else:
        return np.array([], dtype=np.float32), [], failed_ids


def save_embedding_metadata(session, products: list, model_version: str = "clip-vit-b32-v1"):
    """
    Save embedding metadata to the embeddings table.

    Args:
        session: SQLAlchemy session
        products: List of product dicts that were embedded
        model_version: CLIP model version string
    """
    # Get current index size (starting position for new embeddings)
    stats = search_engine.get_index_stats()
    start_idx = stats.get("total_vectors", 0) - len(products)

    for i, product in enumerate(products):
        product_id = product.get("id")
        if product_id is None:
            continue

        vector_index = start_idx + i

        session.execute(text("""
            INSERT INTO embeddings (product_id, embedding_type, model_version, vector_index, created_at)
            VALUES (:product_id, :embedding_type, :model_version, :vector_index, :created_at)
            ON CONFLICT DO NOTHING
        """), {
            "product_id": str(product_id),
            "embedding_type": "image",
            "model_version": model_version,
            "vector_index": vector_index,
            "created_at": datetime.utcnow(),
        })

    session.commit()
    logger.info(f"Saved embedding metadata for {len(products)} products")


def run_pipeline(
    batch_size: int = 32,
    limit: int = 0,
    download_images: bool = True,
    save_index: bool = True,
):
    """
    Run the full embedding pipeline.

    1. Fetch products without embeddings from DB
    2. Generate CLIP embeddings
    3. Add to FAISS index
    4. Save embedding metadata to DB
    5. Save updated FAISS index to disk
    """
    print(f"\n{'='*60}")
    print("Fashion Recommendation - Embedding Pipeline")
    print(f"{'='*60}\n")

    # Database connection
    session, engine = get_db_session()

    try:
        # Step 1: Fetch products
        print("Step 1: Fetching products without embeddings...")
        products = fetch_products_without_embeddings(session, limit)
        print(f"  Found {len(products)} products to process")

        if not products:
            print("  No new products to embed. Pipeline complete.")
            return

        # Step 2: Load CLIP model
        print("\nStep 2: Loading CLIP model...")
        if not clip_service.load_model():
            raise RuntimeError("Failed to load CLIP model")
        print(f"  Model loaded (dim: {clip_service.embedding_dim})")

        # Step 3: Load or create FAISS index
        print("\nStep 3: Loading FAISS index...")
        if os.path.exists(settings.faiss_index_path):
            search_engine.load_index()
            stats = search_engine.get_index_stats()
            print(f"  Existing index loaded: {stats['total_vectors']} vectors")
        else:
            search_engine.create_index(use_hnsw=False)
            print("  Created new empty index")

        # Step 4: Generate embeddings
        print(f"\nStep 4: Generating embeddings (batch_size={batch_size})...")
        embeddings, successful, failed = generate_embeddings_batch(
            products, batch_size=batch_size, download_images=download_images
        )

        print(f"  Successfully embedded: {len(successful)}")
        if failed:
            print(f"  Failed: {len(failed)}")

        if len(successful) == 0:
            print("  No embeddings generated. Pipeline complete.")
            return

        # Step 5: Add to FAISS index
        print("\nStep 5: Adding embeddings to FAISS index...")
        # Convert product dicts for FAISS metadata (stringify UUID)
        products_for_index = []
        for p in successful:
            p_copy = dict(p)
            p_copy["id"] = str(p_copy["id"])
            # Convert Decimal to float for JSON serialization
            if p_copy.get("price") is not None:
                p_copy["price"] = float(p_copy["price"])
            if p_copy.get("original_price") is not None:
                p_copy["original_price"] = float(p_copy["original_price"])
            products_for_index.append(p_copy)

        search_engine.add_embeddings(embeddings, products_for_index)
        stats = search_engine.get_index_stats()
        print(f"  Index now has {stats['total_vectors']} vectors")

        # Step 6: Save embedding metadata
        print("\nStep 6: Saving embedding metadata to database...")
        save_embedding_metadata(session, successful)

        # Step 7: Save FAISS index
        if save_index:
            print("\nStep 7: Saving FAISS index to disk...")
            search_engine.save_index()
            print(f"  Index saved to {settings.faiss_index_path}")

        print(f"\n{'='*60}")
        print(f"Pipeline complete! Processed {len(successful)} products.")
        print(f"{'='*60}\n")

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        raise

    finally:
        session.close()
        engine.dispose()


def run_pipeline_from_json(
    json_path: str,
    batch_size: int = 32,
    limit: int = 0,
    download_images: bool = True,
    save_index: bool = True,
):
    """
    Run embedding pipeline from a scraped JSON file (no database needed).

    Args:
        json_path: Path to the scraped products JSON file
        batch_size: Processing batch size
        limit: Max products to process (0 = all)
        download_images: Whether to download images from URLs
        save_index: Whether to save the index to disk
    """
    print(f"\n{'='*60}")
    print("Fashion Recommendation - Embedding Pipeline (JSON mode)")
    print(f"{'='*60}\n")

    # Step 1: Load products from JSON
    print(f"Step 1: Loading products from {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    if limit > 0:
        products = products[:limit]

    # Ensure each product has an 'id' field
    for p in products:
        if "id" not in p:
            p["id"] = str(uuid.uuid4())

    print(f"  Loaded {len(products)} products")

    if not products:
        print("  No products found in JSON file.")
        return

    # Step 2: Load CLIP model
    print("\nStep 2: Loading CLIP model...")
    if not clip_service.load_model():
        raise RuntimeError("Failed to load CLIP model")
    print(f"  Model loaded (dim: {clip_service.embedding_dim})")

    # Step 3: Load or create FAISS index
    print("\nStep 3: Loading FAISS index...")
    if os.path.exists(settings.faiss_index_path):
        search_engine.load_index()
        stats = search_engine.get_index_stats()
        print(f"  Existing index loaded: {stats['total_vectors']} vectors")
    else:
        search_engine.create_index(use_hnsw=False)
        print("  Created new empty index")

    # Step 4: Generate embeddings
    print(f"\nStep 4: Generating embeddings (batch_size={batch_size})...")
    embeddings, successful, failed = generate_embeddings_batch(
        products, batch_size=batch_size, download_images=download_images
    )

    print(f"  Successfully embedded: {len(successful)}")
    if failed:
        print(f"  Failed: {len(failed)}")

    if len(successful) == 0:
        print("  No embeddings generated. Pipeline complete.")
        return

    # Step 5: Add to FAISS index
    print("\nStep 5: Adding embeddings to FAISS index...")
    products_for_index = []
    for p in successful:
        p_copy = dict(p)
        p_copy["id"] = str(p_copy.get("id", uuid.uuid4()))
        if p_copy.get("price") is not None:
            p_copy["price"] = float(p_copy["price"])
        if p_copy.get("original_price") is not None:
            p_copy["original_price"] = float(p_copy["original_price"])
        products_for_index.append(p_copy)

    search_engine.add_embeddings(embeddings, products_for_index)
    stats = search_engine.get_index_stats()
    print(f"  Index now has {stats['total_vectors']} vectors")

    # Step 6: Save FAISS index
    if save_index:
        print("\nStep 6: Saving FAISS index to disk...")
        search_engine.save_index()
        print(f"  Index saved to {settings.faiss_index_path}")

    print(f"\n{'='*60}")
    print(f"Pipeline complete! Processed {len(successful)} products.")
    print(f"{'='*60}\n")

    # Test search
    print("Testing search with sample query...")
    test_results = search_engine.search_by_text("red dress", k=5)
    print(f"Found {len(test_results)} results for 'red dress':")
    for i, result in enumerate(test_results[:3]):
        print(f"  {i+1}. {result['title']} (similarity: {result['similarity']:.3f})")


def main():
    parser = argparse.ArgumentParser(description="Generate CLIP embeddings for products")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size for embedding generation")
    parser.add_argument("--limit", type=int, default=0, help="Max products to process (0 = all)")
    parser.add_argument("--download-images", action="store_true", help="Download images from URLs")
    parser.add_argument("--no-save", action="store_true", help="Don't save index to disk")
    parser.add_argument("--from-json", type=str, default=None,
                        help="Path to scraped products JSON file (bypasses database)")

    args = parser.parse_args()

    if args.from_json:
        run_pipeline_from_json(
            json_path=args.from_json,
            batch_size=args.batch_size,
            limit=args.limit,
            download_images=args.download_images,
            save_index=not args.no_save,
        )
    else:
        run_pipeline(
            batch_size=args.batch_size,
            limit=args.limit,
            download_images=args.download_images,
            save_index=not args.no_save,
        )


if __name__ == "__main__":
    main()
