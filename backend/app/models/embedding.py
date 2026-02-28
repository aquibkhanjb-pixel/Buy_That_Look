"""Embedding model for tracking vector metadata."""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Embedding(Base):
    """
    Embedding metadata model.

    Tracks the relationship between products and their embeddings in FAISS.
    Actual vectors are stored in FAISS index for efficient search.
    """

    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to product
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Embedding details
    embedding_type = Column(String(20), nullable=False)  # 'image' or 'text'
    model_version = Column(String(50), nullable=False)  # e.g., 'clip-vit-b32-v1'
    vector_index = Column(Integer, nullable=False)  # Position in FAISS index

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    product = relationship("Product", back_populates="embeddings")

    def __repr__(self) -> str:
        return f"<Embedding(id={self.id}, type={self.embedding_type}, index={self.vector_index})>"

    def to_dict(self) -> dict:
        """Convert embedding metadata to dictionary."""
        return {
            "id": self.id,
            "product_id": str(self.product_id),
            "embedding_type": self.embedding_type,
            "model_version": self.model_version,
            "vector_index": self.vector_index,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
