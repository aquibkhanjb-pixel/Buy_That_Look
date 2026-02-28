"""
Generate sample product data, save to database, and build FAISS index.

This script:
1. Creates sample product metadata (fashion-only)
2. Saves products to PostgreSQL database
3. Generates CLIP text-based embeddings for all products
4. Builds and saves FAISS index

Usage:
    python -m scripts.generate_sample_data --num-products 200
    python -m scripts.generate_sample_data --num-products 200 --use-real-images
"""

import os
import sys
import uuid
import random
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from PIL import Image
import requests
from io import BytesIO
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.services.clip_service import clip_service
from app.services.search_engine import search_engine

settings = get_settings()

# ──────────────────────────────────────────────────
# Realistic fashion product data
# ──────────────────────────────────────────────────

CATEGORIES = {
    "Women > Dresses": ["Maxi Dress", "Mini Dress", "Wrap Dress", "Shirt Dress", "Cocktail Dress", "Sundress", "Bodycon Dress", "A-Line Dress", "Evening Gown", "Summer Dress"],
    "Women > Tops": ["Blouse", "T-Shirt", "Crop Top", "Tank Top", "Sweater", "Cardigan", "Turtleneck", "Peplum Top", "Tunic", "Camisole"],
    "Women > Pants": ["Jeans", "Trousers", "Leggings", "Palazzo Pants", "Culottes", "Joggers", "Cargo Pants", "Wide Leg Pants", "Skinny Jeans", "Flare Pants"],
    "Women > Skirts": ["Mini Skirt", "Midi Skirt", "Maxi Skirt", "Pencil Skirt", "Pleated Skirt", "A-Line Skirt", "Wrap Skirt", "Denim Skirt"],
    "Women > Outerwear": ["Blazer", "Trench Coat", "Leather Jacket", "Denim Jacket", "Puffer Jacket", "Wool Coat", "Cardigan", "Cape"],
    "Men > Shirts": ["Dress Shirt", "Polo Shirt", "Oxford Shirt", "Flannel Shirt", "Linen Shirt", "Hawaiian Shirt", "Henley Shirt", "Button-Down Shirt"],
    "Men > T-Shirts": ["Crew Neck T-Shirt", "V-Neck T-Shirt", "Graphic Tee", "Plain T-Shirt", "Longline T-Shirt", "Pocket Tee"],
    "Men > Pants": ["Chinos", "Jeans", "Trousers", "Joggers", "Cargo Pants", "Dress Pants", "Slim Fit Pants", "Straight Fit Jeans"],
    "Men > Jackets": ["Bomber Jacket", "Denim Jacket", "Leather Jacket", "Blazer", "Puffer Jacket", "Windbreaker", "Parka", "Varsity Jacket"],
    "Men > Suits": ["Two-Piece Suit", "Three-Piece Suit", "Tuxedo", "Suit Vest", "Suit Jacket"],
    "Accessories > Bags": ["Tote Bag", "Crossbody Bag", "Backpack", "Clutch", "Shoulder Bag", "Messenger Bag", "Satchel", "Bucket Bag"],
    "Accessories > Sneakers": ["Casual Sneakers", "Running Sneakers", "High-Top Sneakers", "Low-Top Sneakers", "Canvas Sneakers", "Leather Sneakers", "Athletic Sneakers", "Slip-On Sneakers"],
    "Accessories > Shoes": ["Boots", "Heels", "Sandals", "Loafers", "Flats", "Oxford Shoes", "Running Shoes", "Ankle Boots", "Mules", "Slip-Ons", "Derby Shoes", "Chelsea Boots"],
    "Accessories > Jewelry": ["Necklace", "Earrings", "Bracelet", "Ring", "Watch", "Pendant", "Anklet", "Brooch"],
    "Accessories > Sunglasses": ["Aviator Sunglasses", "Wayfarer Sunglasses", "Cat-Eye Sunglasses", "Round Sunglasses", "Oversized Sunglasses"],
    "Accessories > Hats": ["Baseball Cap", "Beanie", "Fedora", "Bucket Hat", "Sun Hat", "Beret"],
}

COLORS = [
    "Red", "Blue", "Black", "White", "Green", "Yellow",
    "Pink", "Purple", "Orange", "Brown", "Gray", "Navy",
    "Beige", "Burgundy", "Teal", "Coral", "Olive", "Maroon",
    "Sky Blue", "Ivory", "Charcoal", "Khaki", "Mustard", "Lavender",
]

BRANDS = [
    "Zara", "H&M", "Nike", "Adidas", "Gucci", "Prada",
    "Levi's", "Gap", "Uniqlo", "Mango", "ASOS", "Forever 21",
    "Topshop", "Ralph Lauren", "Calvin Klein", "Tommy Hilfiger",
    "Versace", "Balenciaga", "Burberry", "Coach", "Michael Kors",
    "Under Armour", "Puma", "Reebok", "New Balance", "Converse",
    "Diesel", "Hugo Boss", "Armani", "Fendi",
]

MATERIALS = [
    "Cotton", "Silk", "Leather", "Denim", "Wool",
    "Polyester", "Linen", "Velvet", "Satin", "Suede",
    "Cashmere", "Chiffon", "Tweed", "Corduroy", "Nylon",
    "Canvas", "Jersey", "Crepe", "Organza", "Fleece",
]

ADJECTIVES = [
    "Elegant", "Casual", "Vintage", "Modern", "Classic",
    "Bohemian", "Sporty", "Chic", "Minimalist", "Bold",
    "Trendy", "Luxurious", "Comfortable", "Slim-Fit", "Oversized",
    "Lightweight", "Premium", "Handcrafted", "Tailored", "Relaxed",
]

PATTERNS = [
    "Solid", "Striped", "Floral", "Plaid", "Polka Dot",
    "Geometric", "Abstract", "Animal Print", "Paisley", "Checkered",
]

SIZES = ["XS", "S", "M", "L", "XL", "XXL", "One Size"]

SOURCE_SITES = ["amazon", "myntra", "asos", "zara", "nordstrom", "hm", "uniqlo"]


def generate_product_title(category: str, color: str, item_type: str) -> str:
    """Generate a realistic product title."""
    adj = random.choice(ADJECTIVES)
    material = random.choice(MATERIALS)
    pattern = random.choice(PATTERNS)

    templates = [
        f"{adj} {color} {material} {item_type}",
        f"{color} {adj} {item_type}",
        f"{material} {item_type} in {color}",
        f"{adj} {pattern} {item_type} - {color}",
        f"{color} {material} {item_type}",
        f"Women's {adj} {color} {item_type}" if "Women" in category else f"Men's {adj} {color} {item_type}",
    ]
    return random.choice(templates)


def generate_product_description(title: str, category: str, material: str, color: str) -> str:
    """Generate a detailed product description."""
    occasions = ["casual outings", "formal events", "everyday wear", "special occasions", "office wear", "weekend brunches", "date nights"]
    fits = ["regular fit", "slim fit", "relaxed fit", "tailored fit", "oversized fit"]
    features = [
        f"Made from premium {material.lower()} fabric",
        f"Available in stunning {color.lower()}",
        f"Features a comfortable {random.choice(fits)}",
        f"Perfect for {random.choice(occasions)}",
        f"Part of our {category.split(' > ')[-1].lower()} collection",
    ]
    return f"{title}. {'. '.join(random.sample(features, 3))}. Machine washable. Imported."


def generate_sample_products(num_products: int = 200) -> list:
    """Generate sample product metadata."""
    products = []
    categories = list(CATEGORIES.keys())

    for i in range(num_products):
        category = random.choice(categories)
        item_types = CATEGORIES[category]
        item_type = random.choice(item_types)
        color = random.choice(COLORS)
        brand = random.choice(BRANDS)
        material = random.choice(MATERIALS)

        title = generate_product_title(category, color, item_type)

        base_price = random.uniform(12.99, 499.99)
        has_discount = random.random() > 0.6

        product = {
            "id": str(uuid.uuid4()),
            "product_id": f"SAMPLE_{i:05d}",
            "title": title,
            "description": generate_product_description(title, category, material, color),
            "price": round(base_price * (0.7 if has_discount else 1.0), 2),
            "original_price": round(base_price, 2) if has_discount else None,
            "currency": "USD",
            "category": category,
            "subcategory": category.split(" > ")[-1],
            "brand": brand,
            "color": color,
            "size": random.choice(SIZES),
            "image_url": f"https://picsum.photos/seed/fashion{i}/400/500",
            "product_url": f"https://example.com/products/SAMPLE_{i:05d}",
            "source_site": random.choice(SOURCE_SITES),
        }
        products.append(product)

    return products


def save_products_to_database(products: list) -> int:
    """Save generated products to PostgreSQL database."""
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()

    saved = 0
    try:
        for product in products:
            # Check if product_id already exists
            exists = session.execute(
                text("SELECT 1 FROM products WHERE product_id = :pid"),
                {"pid": product["product_id"]}
            ).fetchone()

            if exists:
                continue

            session.execute(text("""
                INSERT INTO products (id, product_id, source_site, title, description, brand,
                    price, original_price, currency, category, subcategory, color, size,
                    image_url, product_url, is_active, created_at, updated_at)
                VALUES (:id, :product_id, :source_site, :title, :description, :brand,
                    :price, :original_price, :currency, :category, :subcategory, :color, :size,
                    :image_url, :product_url, true, :now, :now)
            """), {
                **product,
                "now": datetime.utcnow(),
            })
            saved += 1

        session.commit()
        print(f"  Saved {saved} new products to database ({len(products) - saved} already existed)")
    except Exception as e:
        session.rollback()
        print(f"  Database error: {e}")
        raise
    finally:
        session.close()
        engine.dispose()

    return saved


def download_image(url: str, timeout: int = 10) -> bytes:
    """Download image from URL."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"Failed to download image: {e}")
        return None


def create_placeholder_image(width: int = 400, height: int = 500, color: str = "red") -> bytes:
    """Create a placeholder image with solid color."""
    color_map = {
        "red": (255, 0, 0),
        "blue": (0, 0, 255),
        "green": (0, 255, 0),
        "black": (0, 0, 0),
        "white": (255, 255, 255),
        "yellow": (255, 255, 0),
        "pink": (255, 192, 203),
        "purple": (128, 0, 128),
        "orange": (255, 165, 0),
        "brown": (139, 69, 19),
        "gray": (128, 128, 128),
        "navy": (0, 0, 128),
    }

    rgb = color_map.get(color.lower(), (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
    img = Image.new("RGB", (width, height), rgb)

    # Convert to bytes
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


def generate_embeddings_for_products(products: list, use_real_images: bool = False, use_text: bool = True) -> np.ndarray:
    """Generate CLIP embeddings for products.

    Args:
        products: List of product dicts
        use_real_images: Download real images (slow)
        use_text: Use text embeddings from title+description (recommended for sample data)
    """
    print(f"Loading CLIP model...")
    if not clip_service.load_model():
        raise RuntimeError("Failed to load CLIP model")

    embeddings = []

    for i, product in enumerate(products):
        if (i + 1) % 10 == 0:
            print(f"Processing product {i + 1}/{len(products)}...")

        embedding = None

        if use_text:
            # Text-based embedding: much more semantically meaningful for sample data
            text = f"{product['title']}. {product['category']}. {product['color']} {product['brand']}"
            embedding = clip_service.encode_text(text)

        if embedding is None and use_real_images:
            image_bytes = download_image(product["image_url"])
            if image_bytes is not None:
                embedding = clip_service.encode_image(image_bytes)

        if embedding is None and not use_text:
            image_bytes = create_placeholder_image(color=product.get("color", "gray"))
            embedding = clip_service.encode_image(image_bytes)

        if embedding is None:
            print(f"Warning: Failed to encode product {product['product_id']}")
            embedding = np.random.randn(512).astype(np.float32)
            embedding = embedding / np.linalg.norm(embedding)

        embeddings.append(embedding)

    return np.array(embeddings, dtype=np.float32)


def build_index(embeddings: np.ndarray, products: list, output_path: str = None):
    """Build FAISS index from embeddings."""
    print(f"Building FAISS index with {len(embeddings)} vectors...")

    # Create index
    use_hnsw = len(embeddings) > 10000
    search_engine.create_index(use_hnsw=use_hnsw)

    # Add embeddings
    search_engine.add_embeddings(embeddings, products)

    # Save index
    index_path = output_path or settings.faiss_index_path
    search_engine.save_index(index_path)

    print(f"Index saved to {index_path}")
    print(f"Index stats: {search_engine.get_index_stats()}")


def main():
    """Main function to generate sample data and build index."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate sample data and build FAISS index")
    parser.add_argument("--num-products", type=int, default=200, help="Number of sample products")
    parser.add_argument("--use-real-images", action="store_true", help="Download real images (slower)")
    parser.add_argument("--output", type=str, default=None, help="Output path for index")
    parser.add_argument("--no-db", action="store_true", help="Skip saving to database")

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("Fashion Recommendation System - Sample Data Generator")
    print(f"{'='*60}\n")

    # Generate products
    print(f"Step 1: Generating {args.num_products} sample fashion products...")
    products = generate_sample_products(args.num_products)
    print(f"  Generated {len(products)} products")

    # Save to database
    if not args.no_db:
        print(f"\nStep 2: Saving products to database...")
        save_products_to_database(products)
    else:
        print(f"\nStep 2: Skipping database (--no-db)")

    # Generate embeddings (text-based by default for better semantic quality)
    print(f"\nStep 3: Generating CLIP embeddings (text-based)...")
    embeddings = generate_embeddings_for_products(products, use_real_images=args.use_real_images, use_text=True)
    print(f"  Generated {len(embeddings)} embeddings")

    # Build index
    print(f"\nStep 4: Building FAISS index...")
    build_index(embeddings, products, args.output)

    print(f"\n{'='*60}")
    print(f"Sample data generation complete! {len(products)} products.")
    print(f"{'='*60}\n")

    # Test search
    print("Testing search quality...\n")
    test_queries = [
        "red summer dress",
        "men's leather jacket",
        "black running shoes",
        "elegant gold necklace",
        "blue denim jeans",
    ]
    for query in test_queries:
        results = search_engine.search_by_text(query, k=3)
        print(f"  '{query}':")
        for i, r in enumerate(results):
            print(f"    {i+1}. {r['title'][:60]} ({r['category']}) - {r['similarity']:.1%}")
        print()


if __name__ == "__main__":
    main()
