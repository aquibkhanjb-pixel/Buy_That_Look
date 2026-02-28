"""Pydantic schemas for search-related endpoints."""

from typing import Optional, List
from pydantic import BaseModel, Field

from .product import ProductResponse


class SearchFilters(BaseModel):
    """Filters for search queries."""

    min_price: Optional[float] = Field(None, ge=0, description="Minimum price")
    max_price: Optional[float] = Field(None, ge=0, description="Maximum price")
    category: Optional[str] = Field(None, max_length=100, description="Category filter")
    brand: Optional[str] = Field(None, max_length=100, description="Brand filter")
    color: Optional[str] = Field(None, max_length=50, description="Color filter")
    source_site: Optional[str] = Field(None, max_length=50, description="Source site filter")


class TextSearchRequest(BaseModel):
    """Request schema for text-based search."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language search query",
        examples=["blue denim jacket with patches"],
    )
    k: int = Field(
        20,
        ge=1,
        le=100,
        description="Number of results to return",
    )
    filters: Optional[SearchFilters] = None


class HybridSearchRequest(BaseModel):
    """Request schema for hybrid (image + text) search."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Text query to combine with image",
    )
    alpha: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Weight for image embedding (1-alpha for text)",
    )
    k: int = Field(
        20,
        ge=1,
        le=100,
        description="Number of results to return",
    )
    filters: Optional[SearchFilters] = None


class SearchResult(ProductResponse):
    """Individual search result with similarity score."""

    pass


class SearchResponse(BaseModel):
    """Response schema for all search endpoints."""

    query_id: str = Field(..., description="Unique query identifier for logging")
    results: List[SearchResult]
    latency_ms: int = Field(..., ge=0, description="Query processing time in milliseconds")
    total_results: int = Field(..., ge=0, description="Number of results returned")
    filters_applied: Optional[SearchFilters] = None
    model_version: str = Field(default="clip-vit-b32-v1", description="Model used for search")

    class Config:
        json_schema_extra = {
            "example": {
                "query_id": "550e8400-e29b-41d4-a716-446655440000",
                "results": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "product_id": "ASIN123",
                        "title": "Red Floral Summer Dress",
                        "price": 49.99,
                        "currency": "USD",
                        "brand": "Brand Name",
                        "category": "Women > Dresses",
                        "image_url": "https://example.com/image.jpg",
                        "product_url": "https://amazon.com/dp/ASIN123",
                        "source_site": "amazon",
                        "similarity": 0.92,
                    }
                ],
                "latency_ms": 156,
                "total_results": 20,
                "model_version": "clip-vit-b32-v1",
            }
        }
