"""Search API endpoints for image, text, and hybrid search."""

import json
import uuid
import time
from typing import Optional, List

from fastapi import APIRouter, File, UploadFile, Form, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import logger
from app.schemas.search import (
    TextSearchRequest,
    SearchFilters,
    SearchResponse,
    SearchResult,
)
from app.services.search_engine import search_engine
from app.services.cache_service import cache_service
from app.services.search_logger import search_logger
from app.config import get_settings

router = APIRouter()
settings = get_settings()

# Rate limiter (same instance as main.py via app.state)
limiter = Limiter(key_func=get_remote_address)


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


def _filters_to_dict(filters: Optional[SearchFilters]) -> dict:
    """Convert SearchFilters to a plain dict, excluding None values."""
    if not filters:
        return {}
    d = {}
    if filters.min_price is not None:
        d["min_price"] = filters.min_price
    if filters.max_price is not None:
        d["max_price"] = filters.max_price
    if filters.category:
        d["category"] = filters.category
    if filters.brand:
        d["brand"] = filters.brand
    if filters.color:
        d["color"] = filters.color
    return d


@router.post("/image", response_model=SearchResponse)
@limiter.limit("10/minute")
async def search_by_image(
    request: Request,
    image: UploadFile = File(..., description="Image file (JPEG, PNG, WebP)"),
    k: int = Query(default=20, ge=1, le=100, description="Number of results"),
    min_price: Optional[float] = Query(default=None, ge=0),
    max_price: Optional[float] = Query(default=None, ge=0),
    category: Optional[str] = Query(default=None, max_length=100),
    brand: Optional[str] = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    """
    Search for similar products using an uploaded image.

    - Upload a fashion item image (JPEG, PNG, WebP, max 10MB)
    - Returns visually similar products ranked by similarity score
    - Optional filters for price range, category, and brand
    - Rate limited to 10 requests/minute per IP
    """
    start_time = time.time()
    query_id = str(uuid.uuid4())

    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp"]
    if image.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}",
        )

    # Read and validate file size
    content = await image.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {settings.max_upload_size // (1024*1024)}MB",
        )

    # Build filters dict
    filters_dict = {}
    if min_price is not None:
        filters_dict["min_price"] = min_price
    if max_price is not None:
        filters_dict["max_price"] = max_price
    if category:
        filters_dict["category"] = category
    if brand:
        filters_dict["brand"] = brand

    # Check if search engine is ready
    if not search_engine.is_ready():
        logger.warning("Search engine not ready - returning empty results")
        latency_ms = int((time.time() - start_time) * 1000)
        return SearchResponse(
            query_id=query_id,
            results=[],
            latency_ms=latency_ms,
            total_results=0,
            filters_applied=SearchFilters(**filters_dict) if filters_dict else None,
        )

    # Perform search
    raw_results = search_engine.search_by_image(
        image_bytes=content,
        k=k,
        filters=filters_dict if filters_dict else None,
    )

    # Convert to response format
    results = convert_to_search_results(raw_results)
    latency_ms = int((time.time() - start_time) * 1000)

    logger.info(f"Image search completed: {len(results)} results in {latency_ms}ms")

    # Log search to database
    image_hash = search_logger.hash_image(content)
    top_ids = [r.id for r in results[:5]]
    search_logger.log_search(
        db=db,
        query_id=query_id,
        query_type="image",
        image_hash=image_hash,
        filters_applied=json.dumps(filters_dict) if filters_dict else None,
        results_count=len(results),
        top_result_ids=top_ids,
        latency_ms=latency_ms,
    )

    return SearchResponse(
        query_id=query_id,
        results=results,
        latency_ms=latency_ms,
        total_results=len(results),
        filters_applied=SearchFilters(**filters_dict) if filters_dict else None,
    )


@router.post("/text", response_model=SearchResponse)
@limiter.limit("30/minute")
async def search_by_text(
    request: Request,
    body: TextSearchRequest,
    db: Session = Depends(get_db),
):
    """
    Search for products using natural language description.

    - Describe the fashion item you're looking for
    - Returns products matching your description
    - Optional filters for price range, category, and brand
    - Rate limited to 30 requests/minute per IP

    Example queries:
    - "blue denim jacket with patches"
    - "elegant red evening gown"
    - "casual white sneakers"
    """
    start_time = time.time()
    query_id = str(uuid.uuid4())

    filters_dict = _filters_to_dict(body.filters)

    # Check if search engine is ready
    if not search_engine.is_ready():
        logger.warning("Search engine not ready - returning empty results")
        latency_ms = int((time.time() - start_time) * 1000)
        return SearchResponse(
            query_id=query_id,
            results=[],
            latency_ms=latency_ms,
            total_results=0,
            filters_applied=body.filters,
        )

    # Always use search_by_text for correct thresholds and normalization
    raw_results = search_engine.search_by_text(
        query=body.query,
        k=body.k,
        filters=filters_dict if filters_dict else None,
    )

    # Convert to response format
    results = convert_to_search_results(raw_results)
    latency_ms = int((time.time() - start_time) * 1000)

    # Cache the search results
    cache_service.set_search_results("text", body.query, filters_dict, body.k, raw_results)

    logger.info(f"Text search '{body.query[:50]}': {len(results)} results in {latency_ms}ms")

    # Log search to database
    top_ids = [r.id for r in results[:5]]
    search_logger.log_search(
        db=db,
        query_id=query_id,
        query_type="text",
        query_text=body.query,
        filters_applied=json.dumps(filters_dict) if filters_dict else None,
        results_count=len(results),
        top_result_ids=top_ids,
        latency_ms=latency_ms,
    )

    return SearchResponse(
        query_id=query_id,
        results=results,
        latency_ms=latency_ms,
        total_results=len(results),
        filters_applied=body.filters,
    )


@router.post("/hybrid", response_model=SearchResponse)
@limiter.limit("10/minute")
async def search_hybrid(
    request: Request,
    image: UploadFile = File(..., description="Image file"),
    query: str = Form(..., min_length=3, max_length=500),
    alpha: float = Form(default=0.5, ge=0.0, le=1.0),
    k: int = Form(default=20, ge=1, le=100),
    min_price: Optional[float] = Form(default=None),
    max_price: Optional[float] = Form(default=None),
    category: Optional[str] = Form(default=None),
    brand: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    """
    Hybrid search combining image and text.

    - Upload an image AND provide a text description
    - Alpha controls the weight: 1.0 = image only, 0.0 = text only
    - Useful for queries like "find this dress but in blue"
    - Rate limited to 10 requests/minute per IP

    The embeddings are combined using:
    hybrid = alpha * image_embedding + (1-alpha) * text_embedding
    """
    start_time = time.time()
    query_id = str(uuid.uuid4())

    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp"]
    if image.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}",
        )

    # Read and validate file size
    content = await image.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {settings.max_upload_size // (1024*1024)}MB",
        )

    # Build filters
    filters_dict = {}
    if min_price is not None:
        filters_dict["min_price"] = min_price
    if max_price is not None:
        filters_dict["max_price"] = max_price
    if category:
        filters_dict["category"] = category
    if brand:
        filters_dict["brand"] = brand

    filters = SearchFilters(**filters_dict) if filters_dict else None

    # Check if search engine is ready
    if not search_engine.is_ready():
        logger.warning("Search engine not ready - returning empty results")
        latency_ms = int((time.time() - start_time) * 1000)
        return SearchResponse(
            query_id=query_id,
            results=[],
            latency_ms=latency_ms,
            total_results=0,
            filters_applied=filters,
        )

    # For hybrid search, try to use cached text embedding
    from app.services.clip_service import clip_service

    text_embedding = cache_service.get_text_embedding(query)
    if text_embedding is None:
        text_embedding = clip_service.encode_text(query)
        if text_embedding is not None:
            cache_service.set_text_embedding(query, text_embedding)

    image_embedding = clip_service.encode_image(content)

    if image_embedding is None or text_embedding is None:
        logger.error("Failed to encode image or text for hybrid search")
        latency_ms = int((time.time() - start_time) * 1000)
        return SearchResponse(
            query_id=query_id,
            results=[],
            latency_ms=latency_ms,
            total_results=0,
            filters_applied=filters,
        )

    # Combine embeddings
    hybrid_embedding = clip_service.compute_hybrid_embedding(
        image_embedding, text_embedding, alpha
    )

    # Search with hybrid threshold
    raw_results = search_engine.search(
        hybrid_embedding, k, filters_dict if filters_dict else None,
        min_similarity=search_engine.MIN_SIMILARITY_HYBRID,
    )

    # Normalize hybrid similarity scores for display
    low = 0.30 + alpha * 0.15
    high = 0.55 + alpha * 0.25
    span = high - low
    for r in raw_results:
        raw = r["similarity"]
        normalized = min(1.0, max(0.0, (raw - low) / span * 0.40 + 0.60))
        r["similarity"] = round(normalized, 4)

    # Convert to response format
    results = convert_to_search_results(raw_results)
    latency_ms = int((time.time() - start_time) * 1000)

    logger.info(f"Hybrid search (alpha={alpha}) completed: {len(results)} results in {latency_ms}ms")

    # Log search to database
    image_hash = search_logger.hash_image(content)
    top_ids = [r.id for r in results[:5]]
    search_logger.log_search(
        db=db,
        query_id=query_id,
        query_type="hybrid",
        query_text=query,
        image_hash=image_hash,
        filters_applied=json.dumps(filters_dict) if filters_dict else None,
        alpha_value=alpha,
        results_count=len(results),
        top_result_ids=top_ids,
        latency_ms=latency_ms,
    )

    return SearchResponse(
        query_id=query_id,
        results=results,
        latency_ms=latency_ms,
        total_results=len(results),
        filters_applied=filters,
    )


@router.get("/stats")
async def get_search_stats():
    """Get search engine and cache statistics."""
    return {
        "search_engine": search_engine.get_index_stats(),
        "cache": cache_service.get_stats(),
    }
