"""
Full FAISS Index Rebuild - Rebuilds the entire index from database.

Use this when:
- The FAISS index is corrupted or missing
- You want to switch index types (Flat -> HNSW)
- After a major data cleanup
- Periodic full rebuild for optimal search quality

Usage:
    # Rebuild from all products in DB (re-download images)
    python -m scripts.rebuild_index

    # Rebuild using HNSW index (for >100k products)
    python -m scripts.rebuild_index --hnsw

    # Rebuild using text embeddings only (faster, no downloads)
    python -m scripts.rebuild_index --text-only
"""

import os
import sys
import argparse
from pathlib import Path
from io import BytesIO
from datetime import datetime

import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.core.logging import logger
from app.services.clip_service import clip_service
from app.services.search_engine import FashionSearchEngine

settings = get_settings()


def get_db_session():
    """Create a database session."""
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session(), engine


def fetch_all_active_products(session) -> list:
    """Fetch all active products from the database."""
    result = session.execute(text("""
        SELECT id, product_id, title, description, brand,
               price, original_price, currency, category,
               subcategory, color, image_url, additional_images,
               product_url, source_site
        FROM products
        WHERE is_active = TRUE
        ORDER BY created_at
    """))
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]


def rebuild_index(
    use_hnsw: bool = False,
    text_only: bool = False,
    batch_size: int = 32,
    limit: int = 0,
):
    """
    Full index rebuild from database.

    1. Load all active products from DB
    2. Generate CLIP embeddings for all
    3. Build new FAISS index
    4. Replace existing index
    5. Update embeddings table
    """
    print(f"\n{'='*60}")
    print("Fashion Recommendation - Full Index Rebuild")
    print(f"{'='*60}\n")

    session, engine = get_db_session()

    try:
        # Step 1: Fetch all products
        print("Step 1: Fetching all active products...")
        products = fetch_all_active_products(session)
        print(f"  Found {len(products)} active products")

        if limit > 0 and len(products) > limit:
            # Pick products evenly across categories for diversity
            from collections import defaultdict
            by_category = defaultdict(list)
            for p in products:
                by_category[p.get("category", "Other")].append(p)

            num_categories = len(by_category)
            per_category = max(1, limit // num_categories)
            selected = []
            for cat, cat_products in by_category.items():
                selected.extend(cat_products[:per_category])

            # Fill remaining slots with leftover products
            selected_ids = {id(p) for p in selected}
            for p in products:
                if len(selected) >= limit:
                    break
                if id(p) not in selected_ids:
                    selected.append(p)

            products = selected[:limit]
            cats = defaultdict(int)
            for p in products:
                cats[p.get("category", "Other")] += 1
            print(f"  Selected {len(products)} products across {len(cats)} categories:")
            for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
                print(f"    {cat}: {count}")

        if not products:
            print("  No products found. Exiting.")
            return

        # Step 2: Load CLIP model
        print("\nStep 2: Loading CLIP model...")
        if not clip_service.load_model():
            raise RuntimeError("Failed to load CLIP model")
        print(f"  Model loaded (dim: {clip_service.embedding_dim})")

        # Step 3: Generate embeddings
        print(f"\nStep 3: Generating embeddings ({'text-only' if text_only else 'image+text fallback'})...")

        all_embeddings = []
        successful_products = []
        failed_count = 0

        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]

            for product in batch:
                embedding = None

                if text_only:
                    # Text-only mode: use product metadata for embedding
                    title = product.get("title", "")
                    category = product.get("category", "")
                    color = product.get("color", "")
                    brand = product.get("brand", "")
                    subcategory = product.get("subcategory", "")
                    parts = [p for p in [title, category, color, brand, subcategory] if p]
                    text_query = ". ".join(parts)
                    if text_query.strip():
                        embedding = clip_service.encode_text(text_query)
                else:
                    # Image mode: download and encode image (NO text fallback)
                    # Mixing text and image embeddings in the same index causes
                    # text-embedded products to dominate all text search results
                    from scripts.embedding_pipeline import get_image_bytes
                    image_bytes = get_image_bytes(product)
                    if image_bytes:
                        embedding = clip_service.encode_image(image_bytes)

                if embedding is not None:
                    all_embeddings.append(embedding)
                    # Prepare product for FAISS metadata
                    p_copy = dict(product)
                    p_copy["id"] = str(p_copy["id"])
                    if p_copy.get("price") is not None:
                        p_copy["price"] = float(p_copy["price"])
                    if p_copy.get("original_price") is not None:
                        p_copy["original_price"] = float(p_copy["original_price"])
                    successful_products.append(p_copy)
                else:
                    failed_count += 1

            processed = min(i + batch_size, len(products))
            print(f"  Progress: {processed}/{len(products)}")

        print(f"  Embedded: {len(successful_products)}, Failed: {failed_count}")

        if not all_embeddings:
            print("  No embeddings generated. Exiting.")
            return

        embeddings_array = np.array(all_embeddings, dtype=np.float32)

        # Step 4: Build new index
        print(f"\nStep 4: Building {'HNSW' if use_hnsw else 'Flat'} index...")

        # Create a fresh search engine instance to avoid conflicts
        new_engine = FashionSearchEngine.__new__(FashionSearchEngine)
        new_engine.index = None
        new_engine.index_path = settings.faiss_index_path
        new_engine.dimension = 512
        new_engine.id_to_product = {}
        new_engine.product_id_to_index = {}
        new_engine.use_hnsw = False

        new_engine.create_index(use_hnsw=use_hnsw)
        new_engine.add_embeddings(embeddings_array, successful_products)

        stats = {
            "total_vectors": new_engine.index.ntotal,
            "dimension": new_engine.dimension,
            "index_type": "HNSW" if use_hnsw else "Flat",
            "products_mapped": len(new_engine.id_to_product),
        }
        print(f"  Index built: {stats}")

        # Step 5: Save new index (overwrite existing)
        print("\nStep 5: Saving index to disk...")

        # Backup existing index
        if os.path.exists(settings.faiss_index_path):
            backup_path = settings.faiss_index_path + ".backup"
            os.rename(settings.faiss_index_path, backup_path)
            print(f"  Backed up old index to {backup_path}")

        new_engine.save_index()
        print(f"  New index saved to {settings.faiss_index_path}")

        # Step 6: Update embeddings table
        print("\nStep 6: Updating embeddings table...")

        # Clear existing embeddings
        session.execute(text("DELETE FROM embeddings"))

        # Insert new mappings
        for i, product in enumerate(successful_products):
            session.execute(text("""
                INSERT INTO embeddings (product_id, embedding_type, model_version, vector_index, created_at)
                VALUES (:product_id, :embedding_type, :model_version, :vector_index, :created_at)
            """), {
                "product_id": product["id"],
                "embedding_type": "image" if not text_only else "text",
                "model_version": "clip-vit-b32-v1",
                "vector_index": i,
                "created_at": datetime.utcnow(),
            })

        session.commit()
        print(f"  Updated {len(successful_products)} embedding records")

        # Cleanup backup if successful
        backup_path = settings.faiss_index_path + ".backup"
        if os.path.exists(backup_path):
            os.remove(backup_path)
            meta_backup = backup_path.replace(".backup", ".meta.npy.backup")
            if os.path.exists(meta_backup):
                os.remove(meta_backup)

        # Step 7: Test search quality
        print("Search Quality Test")
        print(f"{'-'*40}")

        # Point the global search engine at the new index
        from app.services.search_engine import search_engine
        search_engine.index = new_engine.index
        search_engine.id_to_product = new_engine.id_to_product
        search_engine.product_id_to_index = new_engine.product_id_to_index

        test_queries = [
            "casual sneakers",
            "red summer dress",
            "men's leather jacket",
            "black running shoes",
            "elegant gold necklace",
            "blue denim jeans",
            "white cotton t-shirt",
            "women's handbag",
        ]

        for query in test_queries:
            results = search_engine.search_by_text(query, k=3)
            print(f"  '{query}':")
            if not results:
                print(f"    (no results above threshold)")
            for j, r in enumerate(results):
                print(f"    {j+1}. {r['title'][:55]} ({r.get('category','')}) - {r['similarity']:.1%}")
            print()

        print(f"{'='*60}")
        print(f"Index rebuild complete! {len(successful_products)} products indexed.")
        print(f"Restart the backend server to use the new index.")
        print(f"{'='*60}\n")

    except Exception as e:
        logger.error(f"Rebuild error: {e}")
        # Restore backup if exists
        backup_path = settings.faiss_index_path + ".backup"
        if os.path.exists(backup_path):
            if os.path.exists(settings.faiss_index_path):
                os.remove(settings.faiss_index_path)
            os.rename(backup_path, settings.faiss_index_path)
            print("  Restored backup index due to error")
        raise

    finally:
        session.close()
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Full FAISS index rebuild")
    parser.add_argument("--hnsw", action="store_true", help="Use HNSW index (faster search, approximate)")
    parser.add_argument("--text-only", action="store_true", help="Use text embeddings only (no image downloads)")
    parser.add_argument("--batch-size", type=int, default=32, help="Processing batch size")
    parser.add_argument("--limit", type=int, default=0, help="Max products to embed (0 = all)")

    args = parser.parse_args()

    rebuild_index(
        use_hnsw=args.hnsw,
        text_only=args.text_only,
        batch_size=args.batch_size,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
