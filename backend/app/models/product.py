"""Product model for storing fashion item metadata."""

import json
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Text,
    Numeric,
    Boolean,
    DateTime,
    Index,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY as PG_ARRAY
from sqlalchemy.orm import relationship

from app.core.database import Base


class PortableArray(TypeDecorator):
    """A portable ARRAY type: uses ARRAY on PostgreSQL, JSON text on SQLite."""

    impl = Text
    cache_ok = True

    def __init__(self, item_type=None):
        super().__init__()
        self.item_type = item_type

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_ARRAY(self.item_type or String))
        return dialect.type_descriptor(Text)

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        if value is None:
            return []
        return json.loads(value)


class Product(Base):
    """
    Product model representing a fashion item.

    Stores metadata scraped from e-commerce sites.
    Embeddings are stored separately in FAISS index.
    """

    __tablename__ = "products"

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    # Source identification
    product_id = Column(String(255), unique=True, nullable=False, index=True)
    source_site = Column(String(50), nullable=False)

    # Product details
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    brand = Column(String(100), nullable=True, index=True)

    # Pricing
    price = Column(Numeric(10, 2), nullable=True)
    original_price = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="USD")

    # Categorization
    category = Column(String(100), nullable=True, index=True)
    subcategory = Column(String(100), nullable=True)
    color = Column(String(50), nullable=True)
    size = Column(String(50), nullable=True)

    # Images
    image_url = Column(Text, nullable=False)
    additional_images = Column(PortableArray(Text), default=list)

    # Purchase link
    product_url = Column(Text, nullable=False)

    # Embedding reference
    embedding_id = Column(String(255), nullable=True)
    faiss_index = Column(String(50), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_scraped = Column(DateTime, nullable=True)

    # Relationships
    embeddings = relationship("Embedding", back_populates="product", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_product_category", "category"),
        Index("idx_product_price", "price"),
        Index("idx_product_brand", "brand"),
        Index("idx_product_source", "source_site"),
        Index("idx_product_created", "created_at"),
        Index("idx_product_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, title={self.title[:30]}...)>"

    def to_dict(self) -> dict:
        """Convert product to dictionary for API response."""
        return {
            "id": str(self.id),
            "product_id": self.product_id,
            "title": self.title,
            "description": self.description,
            "brand": self.brand,
            "price": float(self.price) if self.price else None,
            "original_price": float(self.original_price) if self.original_price else None,
            "currency": self.currency,
            "category": self.category,
            "subcategory": self.subcategory,
            "color": self.color,
            "image_url": self.image_url,
            "additional_images": self.additional_images or [],
            "product_url": self.product_url,
            "source_site": self.source_site,
            "is_active": self.is_active,
        }
