"""Pydantic schemas for product-related endpoints."""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


class ProductBase(BaseModel):
    """Base product schema with common fields."""

    title: str
    description: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    currency: str = "USD"
    category: Optional[str] = None
    subcategory: Optional[str] = None
    color: Optional[str] = None


class ProductResponse(ProductBase):
    """Product response schema for search results."""

    id: str
    product_id: str
    image_url: str
    product_url: str
    source_site: str
    similarity: float = Field(..., ge=0.0, le=1.0, description="Similarity score")

    class Config:
        from_attributes = True


class ProductDetail(ProductBase):
    """Detailed product schema with all fields."""

    id: str
    product_id: str
    image_url: str
    additional_images: List[str] = []
    product_url: str
    source_site: str
    size: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductList(BaseModel):
    """Paginated list of products."""

    items: List[ProductDetail]
    total: int
    page: int = 1
    page_size: int = 20
    has_more: bool = False
