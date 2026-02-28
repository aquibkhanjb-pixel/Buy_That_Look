"""
Fashion Search Engine using FAISS for vector similarity search.

Handles index management, similarity search, and result retrieval.
Supports both exact (Flat) and approximate (HNSW) search algorithms.
"""

import os
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

import numpy as np
import faiss

from app.config import get_settings
from app.core.logging import logger
from app.services.clip_service import clip_service

settings = get_settings()


class FashionSearchEngine:
    """
    FAISS-based search engine for fashion product similarity search.

    Features:
    - Exact search (IndexFlatIP) for small catalogs
    - Approximate search (IndexHNSWFlat) for large catalogs
    - Index persistence (save/load)
    - Product metadata mapping
    """

    _instance: Optional["FashionSearchEngine"] = None
    _initialized: bool = False

    def __new__(cls) -> "FashionSearchEngine":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize search engine."""
        if FashionSearchEngine._initialized:
            return

        self.index: Optional[faiss.Index] = None
        self.index_path = settings.faiss_index_path
        self.dimension = 512  # CLIP ViT-B/32 embedding dimension

        # Mapping from FAISS index position to product data
        self.id_to_product: Dict[int, Dict[str, Any]] = {}
        self.product_id_to_index: Dict[str, int] = {}

        # Index configuration
        self.use_hnsw = False  # Use flat index by default, HNSW for >100k products

        logger.info("FashionSearchEngine initialized")
        FashionSearchEngine._initialized = True

    def create_index(self, use_hnsw: bool = False, hnsw_m: int = 32) -> bool:
        """
        Create a new FAISS index.

        Args:
            use_hnsw: Use HNSW index for faster approximate search
            hnsw_m: HNSW parameter (connections per layer)

        Returns:
            bool: True if index created successfully
        """
        try:
            if use_hnsw:
                # HNSW index for large catalogs (>100k products)
                # Approximate but fast
                self.index = faiss.IndexHNSWFlat(self.dimension, hnsw_m)
                self.index.hnsw.efConstruction = 200  # Build quality
                self.index.hnsw.efSearch = 64  # Search quality
                self.use_hnsw = True
                logger.info(f"Created HNSW index (M={hnsw_m})")
            else:
                # Flat index for exact search (small catalogs)
                # Inner Product = cosine similarity for normalized vectors
                self.index = faiss.IndexFlatIP(self.dimension)
                self.use_hnsw = False
                logger.info("Created Flat index (exact search)")

            return True

        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            return False

    def load_index(self, path: Optional[str] = None) -> bool:
        """
        Load existing FAISS index from disk.

        Args:
            path: Path to index file (uses default if None)

        Returns:
            bool: True if loaded successfully
        """
        index_path = path or self.index_path

        if not os.path.exists(index_path):
            logger.warning(f"Index file not found: {index_path}")
            return False

        try:
            self.index = faiss.read_index(index_path)
            logger.info(f"Loaded index with {self.index.ntotal} vectors")

            # Load metadata mapping
            metadata_path = index_path + ".meta.npy"
            if os.path.exists(metadata_path):
                metadata = np.load(metadata_path, allow_pickle=True).item()
                self.id_to_product = metadata.get("id_to_product", {})
                self.product_id_to_index = metadata.get("product_id_to_index", {})
                logger.info(f"Loaded metadata for {len(self.id_to_product)} products")

            return True

        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return False

    def save_index(self, path: Optional[str] = None) -> bool:
        """
        Save FAISS index to disk.

        Args:
            path: Path to save index (uses default if None)

        Returns:
            bool: True if saved successfully
        """
        if self.index is None:
            logger.error("No index to save")
            return False

        index_path = path or self.index_path

        try:
            # Ensure directory exists
            Path(index_path).parent.mkdir(parents=True, exist_ok=True)

            # Save index
            faiss.write_index(self.index, index_path)
            logger.info(f"Saved index to {index_path}")

            # Save metadata
            metadata = {
                "id_to_product": self.id_to_product,
                "product_id_to_index": self.product_id_to_index,
            }
            np.save(index_path + ".meta.npy", metadata)
            logger.info("Saved index metadata")

            return True

        except Exception as e:
            logger.error(f"Failed to save index: {e}")
            return False

    def add_embeddings(
        self,
        embeddings: np.ndarray,
        products: List[Dict[str, Any]]
    ) -> bool:
        """
        Add embeddings and product metadata to the index.

        Args:
            embeddings: Array of shape (N, 512) with embeddings
            products: List of product metadata dicts

        Returns:
            bool: True if added successfully
        """
        if self.index is None:
            logger.error("Index not initialized. Call create_index() first.")
            return False

        if len(embeddings) != len(products):
            logger.error("Number of embeddings must match number of products")
            return False

        try:
            # Get starting index position
            start_idx = self.index.ntotal

            # Add embeddings to FAISS
            embeddings = embeddings.astype(np.float32)
            self.index.add(embeddings)

            # Update metadata mappings
            for i, product in enumerate(products):
                idx = start_idx + i
                self.id_to_product[idx] = product
                if "id" in product:
                    self.product_id_to_index[product["id"]] = idx

            logger.info(f"Added {len(embeddings)} embeddings (total: {self.index.ntotal})")
            return True

        except Exception as e:
            logger.error(f"Failed to add embeddings: {e}")
            return False

    # Minimum similarity thresholds by search type
    # Image-to-image: only show highly similar items (85%+)
    # Hybrid: medium threshold — blended embedding has intermediate similarity range
    # Text-to-image: low threshold — CLIP cross-modal alignment ~0.20-0.35
    MIN_SIMILARITY_IMAGE = 0.85
    MIN_SIMILARITY_TEXT = 0.18
    MIN_SIMILARITY_HYBRID = 0.35
    MIN_SIMILARITY_THRESHOLD = 0.18  # Default fallback

    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        min_similarity: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar products.

        Args:
            query_embedding: Query embedding (512-dim)
            k: Number of results to return
            filters: Optional filters (price_range, category, etc.)
            min_similarity: Minimum similarity score (0-1). Results below
                this threshold are excluded. Uses class default if None.

        Returns:
            List of product dicts with similarity scores
        """
        if self.index is None or self.index.ntotal == 0:
            logger.warning("Index is empty or not loaded")
            return []

        threshold = min_similarity if min_similarity is not None else self.MIN_SIMILARITY_THRESHOLD

        try:
            # Ensure correct shape
            query_embedding = query_embedding.astype(np.float32)
            if query_embedding.ndim == 1:
                query_embedding = query_embedding.reshape(1, -1)

            # Fetch more results if filtering (to have enough after filter)
            fetch_k = min(k * 3 if filters else k, self.index.ntotal)

            # Search
            similarities, indices = self.index.search(query_embedding, fetch_k)

            # Build results
            results = []
            for sim, idx in zip(similarities[0], indices[0]):
                if idx < 0:  # FAISS returns -1 for empty slots
                    continue

                # Apply similarity threshold
                if float(sim) < threshold:
                    continue

                product = self.id_to_product.get(int(idx))
                if product is None:
                    continue

                # Apply filters
                if filters and not self._matches_filters(product, filters):
                    continue

                result = {
                    **product,
                    "similarity": float(sim),
                    "faiss_index": int(idx),
                }
                results.append(result)

                if len(results) >= k:
                    break

            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _matches_filters(self, product: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if product matches all filters."""
        # Price range filter
        if "min_price" in filters and filters["min_price"] is not None:
            price = product.get("price")
            if price is None or price < filters["min_price"]:
                return False

        if "max_price" in filters and filters["max_price"] is not None:
            price = product.get("price")
            if price is None or price > filters["max_price"]:
                return False

        # Category filter (case-insensitive partial match)
        if "category" in filters and filters["category"]:
            product_category = product.get("category", "").lower()
            if filters["category"].lower() not in product_category:
                return False

        # Brand filter
        if "brand" in filters and filters["brand"]:
            product_brand = product.get("brand", "").lower()
            if filters["brand"].lower() not in product_brand:
                return False

        # Color filter
        if "color" in filters and filters["color"]:
            product_color = product.get("color", "").lower()
            if filters["color"].lower() not in product_color:
                return False

        return True

    def search_by_image(
        self,
        image_bytes: bytes,
        k: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search by image upload.

        Args:
            image_bytes: Raw image bytes
            k: Number of results
            filters: Optional filters

        Returns:
            List of similar products
        """
        # Generate embedding
        embedding = clip_service.encode_image(image_bytes)
        if embedding is None:
            logger.error("Failed to encode image")
            return []

        return self.search(embedding, k, filters, min_similarity=self.MIN_SIMILARITY_IMAGE)

    def search_by_text(
        self,
        query: str,
        k: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search by text description.

        Args:
            query: Natural language query
            k: Number of results
            filters: Optional filters

        Returns:
            List of matching products
        """
        # Generate embedding
        embedding = clip_service.encode_text(query)
        if embedding is None:
            logger.error("Failed to encode text")
            return []

        results = self.search(embedding, k, filters, min_similarity=self.MIN_SIMILARITY_TEXT)

        self._normalize_text_scores(results)

        return results

    @staticmethod
    def _normalize_text_scores(results: List[Dict[str, Any]]) -> None:
        """
        Normalize text-to-image CLIP similarity scores for display.

        CLIP cross-modal (text→image) raw similarity is typically 0.18–0.38.
        We map this to a user-friendly 55%–95% display range.
        """
        for r in results:
            raw = r["similarity"]
            # Map [0.18, 0.38] → [0.55, 0.95]
            normalized = min(0.99, max(0.50, (raw - 0.18) / 0.20 * 0.40 + 0.55))
            r["similarity"] = round(normalized, 4)

    def search_hybrid(
        self,
        image_bytes: bytes,
        query: str,
        alpha: float = 0.5,
        k: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining image and text.

        Args:
            image_bytes: Raw image bytes
            query: Text query
            alpha: Weight for image (0-1)
            k: Number of results
            filters: Optional filters

        Returns:
            List of matching products
        """
        # Generate embeddings
        image_embedding = clip_service.encode_image(image_bytes)
        text_embedding = clip_service.encode_text(query)

        if image_embedding is None or text_embedding is None:
            logger.error("Failed to encode image or text")
            return []

        # Combine embeddings
        hybrid_embedding = clip_service.compute_hybrid_embedding(
            image_embedding, text_embedding, alpha
        )

        results = self.search(hybrid_embedding, k, filters, min_similarity=self.MIN_SIMILARITY_HYBRID)

        # Normalize hybrid similarity scores for display
        # Hybrid embedding produces scores between text-only and image-only ranges.
        # With alpha=0.5, typical range is [0.35, 0.75] → display [0.60, 1.0]
        # Adjust normalization based on alpha (more image weight → higher raw scores)
        low = 0.30 + alpha * 0.15   # alpha=0: 0.30, alpha=0.5: 0.375, alpha=1: 0.45
        high = 0.55 + alpha * 0.25  # alpha=0: 0.55, alpha=0.5: 0.675, alpha=1: 0.80
        span = high - low
        for r in results:
            raw = r["similarity"]
            normalized = min(1.0, max(0.0, (raw - low) / span * 0.40 + 0.60))
            r["similarity"] = round(normalized, 4)

        return results

    def get_similar_to_product(
        self,
        product_id: str,
        k: int = 20,
        exclude_self: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find products similar to a given product.

        Args:
            product_id: Product ID to find similar items for
            k: Number of results
            exclude_self: Whether to exclude the query product

        Returns:
            List of similar products
        """
        if product_id not in self.product_id_to_index:
            logger.warning(f"Product not found in index: {product_id}")
            return []

        idx = self.product_id_to_index[product_id]

        # Get embedding from index
        try:
            embedding = self.index.reconstruct(idx)
        except RuntimeError:
            # Some index types don't support reconstruction
            logger.error("Index doesn't support embedding reconstruction")
            return []

        # Search
        results = self.search(embedding, k + 1 if exclude_self else k)

        # Exclude self if requested
        if exclude_self:
            results = [r for r in results if r.get("id") != product_id][:k]

        return results

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the current index."""
        if self.index is None:
            return {"status": "not_initialized"}

        return {
            "status": "loaded",
            "total_vectors": self.index.ntotal,
            "dimension": self.dimension,
            "index_type": "HNSW" if self.use_hnsw else "Flat",
            "products_mapped": len(self.id_to_product),
        }

    def is_ready(self) -> bool:
        """Check if search engine is ready for queries."""
        return self.index is not None and self.index.ntotal > 0


# Global instance
search_engine = FashionSearchEngine()
