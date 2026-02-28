"""
Search logging service for recording queries to the database.

Logs every search request asynchronously for analytics:
- Popular search queries
- Search latency tracking
- Click-through rate analysis
- Result quality monitoring
"""

import hashlib
from typing import Optional, List

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.search_log import SearchLog


class SearchLogger:
    """Service for logging search queries to the database."""

    @staticmethod
    def log_search(
        db: Session,
        query_id: str,
        query_type: str,
        query_text: Optional[str] = None,
        image_hash: Optional[str] = None,
        filters_applied: Optional[str] = None,
        alpha_value: Optional[float] = None,
        results_count: int = 0,
        top_result_ids: Optional[List[str]] = None,
        latency_ms: int = 0,
    ) -> bool:
        """
        Record a search query in the database.

        Args:
            db: Database session
            query_id: Unique query identifier
            query_type: 'image', 'text', or 'hybrid'
            query_text: Text query (for text/hybrid searches)
            image_hash: Hash of uploaded image (for image/hybrid)
            filters_applied: JSON string of applied filters
            alpha_value: Alpha weight (hybrid search only)
            results_count: Number of results returned
            top_result_ids: IDs of top 5 results
            latency_ms: Processing time in milliseconds

        Returns:
            True if logged successfully
        """
        try:
            log_entry = SearchLog(
                session_id=query_id,
                query_type=query_type,
                query_text=query_text,
                query_image_hash=image_hash,
                filters_applied=filters_applied,
                alpha_value=str(alpha_value) if alpha_value is not None else None,
                results_count=results_count,
                top_result_ids=top_result_ids or [],
                latency_ms=latency_ms,
            )

            db.add(log_entry)
            db.commit()

            logger.debug(
                f"Search logged: type={query_type}, results={results_count}, "
                f"latency={latency_ms}ms"
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to log search: {e}")
            db.rollback()
            return False

    @staticmethod
    def hash_image(image_bytes: bytes) -> str:
        """Generate a hash for an uploaded image."""
        return hashlib.sha256(image_bytes).hexdigest()[:16]


# Global instance
search_logger = SearchLogger()
