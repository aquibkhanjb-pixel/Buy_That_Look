"""Search log model for analytics and improving results."""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from app.core.database import Base
from app.models.product import PortableArray


class SearchLog(Base):
    """
    Search log model for tracking user queries.

    Used for:
    - Analytics (popular searches, trends)
    - Improving search results
    - Click-through rate analysis
    """

    __tablename__ = "search_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Session tracking
    session_id = Column(String(255), nullable=True, index=True)

    # Query details
    query_type = Column(String(20), nullable=False)  # 'image', 'text', 'hybrid'
    query_text = Column(Text, nullable=True)  # For text/hybrid searches
    query_image_hash = Column(String(64), nullable=True)  # Hash of uploaded image

    # Search parameters
    filters_applied = Column(Text, nullable=True)  # JSON string of filters
    alpha_value = Column(String(10), nullable=True)  # For hybrid search

    # Results
    results_count = Column(Integer, nullable=True)
    top_result_ids = Column(PortableArray(String), default=list)  # First 5 result IDs

    # Performance
    latency_ms = Column(Integer, nullable=True)

    # User interaction
    clicked_products = Column(PortableArray(String), default=list)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<SearchLog(id={self.id}, type={self.query_type})>"

    def to_dict(self) -> dict:
        """Convert search log to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "query_type": self.query_type,
            "query_text": self.query_text,
            "results_count": self.results_count,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
