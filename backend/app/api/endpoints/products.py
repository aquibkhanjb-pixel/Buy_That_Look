"""Product API endpoints."""

import time
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import logger
from app.models.product import Product
from app.schemas.product import ProductDetail, ProductList
from app.schemas.search import SearchResponse, SearchResult
from app.config import get_settings

router = APIRouter()
settings = get_settings()


def convert_to_search_results(raw_results: List[dict]) -> List[SearchResult]:
    """Convert raw search results to SearchResult schema."""
    results = []
    for item in raw_results:
        try:
            result = SearchResult(
                id=str(item.get("id", "")),
                product_id=item.get("product_id", ""),
                title=item.get("title", "Unknown"),
                description=item.get("description"),
                brand=item.get("brand"),
                price=item.get("price"),
                original_price=item.get("original_price"),
                currency=item.get("currency", "USD"),
                category=item.get("category"),
                subcategory=item.get("subcategory"),
                color=item.get("color"),
                image_url=item.get("image_url", ""),
                product_url=item.get("product_url", ""),
                source_site=item.get("source_site", ""),
                similarity=item.get("similarity", 0.0),
            )
            results.append(result)
        except Exception as e:
            logger.warning(f"Failed to convert search result: {e}")
            continue
    return results


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(
    product_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get detailed information about a specific product.

    Returns all product metadata including additional images and specifications.
    """
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductDetail(
        id=str(product.id),
        product_id=product.product_id,
        title=product.title,
        description=product.description,
        brand=product.brand,
        price=float(product.price) if product.price else None,
        original_price=float(product.original_price) if product.original_price else None,
        currency=product.currency,
        category=product.category,
        subcategory=product.subcategory,
        color=product.color,
        size=product.size,
        image_url=product.image_url,
        additional_images=product.additional_images or [],
        product_url=product.product_url,
        source_site=product.source_site,
        is_active=product.is_active,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.get("/{product_id}/similar", response_model=SearchResponse)
async def get_similar_products(
    product_id: UUID,
    k: int = Query(default=20, ge=1, le=100, description="Number of results"),
    db: Session = Depends(get_db),
):
    """
    Get products similar to the specified product.

    Uses the product's pre-computed embedding to find visually similar items.
    """
    start_time = time.time()

    # Similar product search via FAISS has been removed (AI chat assistant handles recommendations)
    return SearchResponse(
        query_id=str(product_id),
        results=[],
        latency_ms=0,
        total_results=0,
    )


@router.get("/", response_model=ProductList)
async def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    min_price: Optional[float] = Query(default=None, ge=0),
    max_price: Optional[float] = Query(default=None, ge=0),
    db: Session = Depends(get_db),
):
    """
    List products with optional filtering and pagination.

    Useful for browsing the catalog without a specific search query.
    """
    query = db.query(Product).filter(Product.is_active == True)

    # Apply filters
    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    # Get total count
    total = query.count()

    # Paginate
    offset = (page - 1) * page_size
    products = query.order_by(Product.created_at.desc()).offset(offset).limit(page_size).all()

    # Convert to response format
    items = [
        ProductDetail(
            id=str(p.id),
            product_id=p.product_id,
            title=p.title,
            description=p.description,
            brand=p.brand,
            price=float(p.price) if p.price else None,
            original_price=float(p.original_price) if p.original_price else None,
            currency=p.currency,
            category=p.category,
            subcategory=p.subcategory,
            color=p.color,
            size=p.size,
            image_url=p.image_url,
            additional_images=p.additional_images or [],
            product_url=p.product_url,
            source_site=p.source_site,
            is_active=p.is_active,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in products
    ]

    return ProductList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(products)) < total,
    )
