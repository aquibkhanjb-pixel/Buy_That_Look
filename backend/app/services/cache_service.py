"""
Redis caching service for embedding and search result caching.

Caches text query embeddings to avoid redundant CLIP inference.
Uses configurable TTL and serialization for numpy arrays.
"""

import hashlib
import json
from typing import Optional, Any

import numpy as np
import redis

from app.config import get_settings
from app.core.logging import logger

settings = get_settings()


class CacheService:
    """
    Redis-based caching service.

    Caches:
    - Text embeddings (keyed by query hash) — avoids re-running CLIP for repeated queries
    - Search results (keyed by query+filters hash) — avoids re-searching for identical requests
    """

    _instance: Optional["CacheService"] = None
    _initialized: bool = False

    def __new__(cls) -> "CacheService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if CacheService._initialized:
            return

        self.client: Optional[redis.Redis] = None
        self.connected = False

        # TTL settings (seconds)
        self.text_embedding_ttl = 3600       # 1 hour for text embeddings
        self.search_result_ttl = 300         # 5 minutes for search results

        # Key prefixes
        self.TEXT_EMBED_PREFIX = "emb:text:"
        self.SEARCH_RESULT_PREFIX = "search:"

        CacheService._initialized = True

    def connect(self) -> bool:
        """Establish connection to Redis."""
        try:
            self.client = redis.from_url(
                settings.redis_url,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            # Test connection
            self.client.ping()
            self.connected = True
            logger.info(f"Redis connected: {settings.redis_url}")
            return True
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Caching disabled.")
            self.connected = False
            return False

    def is_connected(self) -> bool:
        """Check if Redis is connected and responsive."""
        if not self.client:
            return False
        try:
            self.client.ping()
            self.connected = True
            return True
        except Exception:
            self.connected = False
            return False

    # ─── Text Embedding Cache ────────────────────────────────────

    @staticmethod
    def _hash_query(query: str) -> str:
        """Generate a deterministic hash for a text query."""
        normalized = query.strip().lower()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def get_text_embedding(self, query: str) -> Optional[np.ndarray]:
        """
        Retrieve cached text embedding.

        Args:
            query: The text query

        Returns:
            np.ndarray if cached, None if miss or error
        """
        if not self.connected:
            return None

        key = f"{self.TEXT_EMBED_PREFIX}{self._hash_query(query)}"

        try:
            data = self.client.get(key)
            if data is None:
                return None

            embedding = np.frombuffer(data, dtype=np.float32).copy()
            logger.debug(f"Cache HIT for text embedding: '{query[:30]}...'")
            return embedding

        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    def set_text_embedding(self, query: str, embedding: np.ndarray) -> bool:
        """
        Cache a text embedding.

        Args:
            query: The text query
            embedding: The 512-dim embedding vector

        Returns:
            True if cached successfully
        """
        if not self.connected:
            return False

        key = f"{self.TEXT_EMBED_PREFIX}{self._hash_query(query)}"

        try:
            data = embedding.astype(np.float32).tobytes()
            self.client.setex(key, self.text_embedding_ttl, data)
            logger.debug(f"Cached text embedding: '{query[:30]}...'")
            return True

        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    # ─── Search Result Cache ─────────────────────────────────────

    @staticmethod
    def _hash_search_key(query_type: str, query_text: str, filters: Optional[dict], k: int) -> str:
        """Generate a deterministic hash for a search request."""
        raw = json.dumps({
            "type": query_type,
            "query": query_text.strip().lower() if query_text else "",
            "filters": filters or {},
            "k": k,
        }, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def get_search_results(
        self, query_type: str, query_text: str, filters: Optional[dict], k: int
    ) -> Optional[list]:
        """Retrieve cached search results."""
        if not self.connected:
            return None

        key = f"{self.SEARCH_RESULT_PREFIX}{self._hash_search_key(query_type, query_text, filters, k)}"

        try:
            data = self.client.get(key)
            if data is None:
                return None

            results = json.loads(data.decode("utf-8"))
            logger.debug(f"Cache HIT for search results: {query_type}")
            return results

        except Exception as e:
            logger.warning(f"Search cache get error: {e}")
            return None

    def set_search_results(
        self, query_type: str, query_text: str, filters: Optional[dict], k: int, results: list
    ) -> bool:
        """Cache search results."""
        if not self.connected:
            return False

        key = f"{self.SEARCH_RESULT_PREFIX}{self._hash_search_key(query_type, query_text, filters, k)}"

        try:
            data = json.dumps(results).encode("utf-8")
            self.client.setex(key, self.search_result_ttl, data)
            logger.debug(f"Cached search results: {query_type}")
            return True

        except Exception as e:
            logger.warning(f"Search cache set error: {e}")
            return False

    # ─── Cache Management ────────────────────────────────────────

    def clear_all(self) -> bool:
        """Flush all cached data."""
        if not self.connected:
            return False
        try:
            self.client.flushdb()
            logger.info("Cache cleared")
            return True
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return False

    def get_stats(self) -> dict:
        """Get cache statistics."""
        if not self.connected:
            return {"status": "disconnected"}

        try:
            info = self.client.info(section="stats")
            memory = self.client.info(section="memory")
            return {
                "status": "connected",
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "used_memory_human": memory.get("used_memory_human", "N/A"),
                "total_keys": self.client.dbsize(),
            }
        except Exception as e:
            return {"status": "error", "detail": str(e)}


# Global instance
cache_service = CacheService()
