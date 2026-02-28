"""
Unit tests for backend services.

Tests:
- CLIPService (via mock): encode_image, encode_text, hybrid, similarity
- FashionSearchEngine: create, add, search, filters
- CacheService (via mock): get/set embeddings, get/set results
- SearchLogger: log_search
"""

import numpy as np
import pytest
import faiss

from tests.conftest import (
    MockCLIPService,
    MockCacheService,
    make_product,
    make_products,
    create_test_image,
)


# ═══════════════════════════════════════════════════════════════════
# CLIP Service Tests
# ═══════════════════════════════════════════════════════════════════

class TestCLIPService:
    """Tests for CLIP embedding service (via mock)."""

    def test_is_loaded(self, mock_clip):
        assert mock_clip.is_loaded() is True

    def test_load_model(self, mock_clip):
        assert mock_clip.load_model() is True

    def test_encode_image_returns_correct_shape(self, mock_clip):
        image_bytes = create_test_image()
        embedding = mock_clip.encode_image(image_bytes)

        assert embedding is not None
        assert embedding.shape == (512,)
        assert embedding.dtype == np.float32

    def test_encode_image_is_normalized(self, mock_clip):
        image_bytes = create_test_image()
        embedding = mock_clip.encode_image(image_bytes)

        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 1e-5, f"Embedding norm should be ~1.0, got {norm}"

    def test_encode_text_returns_correct_shape(self, mock_clip):
        embedding = mock_clip.encode_text("red summer dress")

        assert embedding is not None
        assert embedding.shape == (512,)
        assert embedding.dtype == np.float32

    def test_encode_text_is_normalized(self, mock_clip):
        embedding = mock_clip.encode_text("blue denim jacket")

        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 1e-5

    def test_encode_text_deterministic(self, mock_clip):
        """Same text should produce same embedding."""
        emb1 = mock_clip.encode_text("red dress")
        emb2 = mock_clip.encode_text("red dress")

        np.testing.assert_array_equal(emb1, emb2)

    def test_encode_text_different_for_different_queries(self, mock_clip):
        """Different text should produce different embeddings."""
        emb1 = mock_clip.encode_text("red dress")
        emb2 = mock_clip.encode_text("blue jacket")

        assert not np.array_equal(emb1, emb2)

    def test_hybrid_embedding_shape(self, mock_clip):
        image_emb = mock_clip.encode_image(create_test_image())
        text_emb = mock_clip.encode_text("test query")

        hybrid = mock_clip.compute_hybrid_embedding(image_emb, text_emb, alpha=0.5)

        assert hybrid.shape == (512,)
        assert hybrid.dtype == np.float32

    def test_hybrid_embedding_is_normalized(self, mock_clip):
        image_emb = mock_clip.encode_image(create_test_image())
        text_emb = mock_clip.encode_text("test query")

        hybrid = mock_clip.compute_hybrid_embedding(image_emb, text_emb, alpha=0.7)

        norm = np.linalg.norm(hybrid)
        assert abs(norm - 1.0) < 1e-5

    def test_hybrid_alpha_one_equals_image(self, mock_clip):
        """Alpha=1.0 should return the image embedding."""
        image_emb = mock_clip.encode_image(create_test_image())
        text_emb = mock_clip.encode_text("test query")

        hybrid = mock_clip.compute_hybrid_embedding(image_emb, text_emb, alpha=1.0)

        # Should be image_emb normalized (which it already is)
        np.testing.assert_array_almost_equal(hybrid, image_emb, decimal=5)

    def test_hybrid_alpha_zero_equals_text(self, mock_clip):
        """Alpha=0.0 should return the text embedding."""
        image_emb = mock_clip.encode_image(create_test_image())
        text_emb = mock_clip.encode_text("test query")

        hybrid = mock_clip.compute_hybrid_embedding(image_emb, text_emb, alpha=0.0)

        np.testing.assert_array_almost_equal(hybrid, text_emb, decimal=5)

    def test_batch_encode_images(self, mock_clip):
        images = [create_test_image(color=c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]]
        embeddings = mock_clip.encode_images_batch(images)

        assert embeddings.shape == (3, 512)
        assert embeddings.dtype == np.float32

    def test_batch_encode_texts(self, mock_clip):
        texts = ["red dress", "blue jacket", "white sneakers"]
        embeddings = mock_clip.encode_texts_batch(texts)

        assert embeddings.shape == (3, 512)

    def test_compute_similarity(self, mock_clip):
        query = mock_clip.encode_text("red dress")
        targets = mock_clip.encode_texts_batch(["red dress", "blue jacket", "green hat"])

        similarities = mock_clip.compute_similarity(query, targets)

        assert similarities.shape == (3,)
        # Self-similarity should be highest
        assert similarities[0] == max(similarities)


# ═══════════════════════════════════════════════════════════════════
# Search Engine Tests
# ═══════════════════════════════════════════════════════════════════

class TestSearchEngine:
    """Tests for FAISS-based search engine."""

    def _create_engine(self):
        """Create a fresh search engine instance for testing."""
        from app.services.search_engine import FashionSearchEngine

        engine = FashionSearchEngine.__new__(FashionSearchEngine)
        engine.index = None
        engine.index_path = "/tmp/test_index.faiss"
        engine.dimension = 512
        engine.id_to_product = {}
        engine.product_id_to_index = {}
        engine.use_hnsw = False
        return engine

    def test_create_flat_index(self):
        engine = self._create_engine()
        result = engine.create_index(use_hnsw=False)

        assert result is True
        assert engine.index is not None
        assert engine.index.ntotal == 0

    def test_create_hnsw_index(self):
        engine = self._create_engine()
        result = engine.create_index(use_hnsw=True)

        assert result is True
        assert engine.use_hnsw is True

    def test_add_embeddings(self):
        engine = self._create_engine()
        engine.create_index()

        products = make_products(5)
        embeddings = np.random.randn(5, 512).astype(np.float32)
        # Normalize
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        result = engine.add_embeddings(embeddings, products)

        assert result is True
        assert engine.index.ntotal == 5
        assert len(engine.id_to_product) == 5

    def test_add_embeddings_mismatched_count(self):
        engine = self._create_engine()
        engine.create_index()

        products = make_products(3)
        embeddings = np.random.randn(5, 512).astype(np.float32)

        result = engine.add_embeddings(embeddings, products)
        assert result is False

    def test_search_returns_results(self):
        engine = self._create_engine()
        engine.create_index()

        products = make_products(10)
        embeddings = np.random.randn(10, 512).astype(np.float32)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        engine.add_embeddings(embeddings, products)

        # Search with first product's embedding
        results = engine.search(embeddings[0], k=5)

        assert len(results) == 5
        assert results[0]["similarity"] >= results[1]["similarity"]  # Sorted by similarity
        assert "title" in results[0]

    def test_search_empty_index(self):
        engine = self._create_engine()
        engine.create_index()

        query = np.random.randn(512).astype(np.float32)
        results = engine.search(query, k=5)

        assert results == []

    def test_search_no_index(self):
        engine = self._create_engine()

        query = np.random.randn(512).astype(np.float32)
        results = engine.search(query, k=5)

        assert results == []

    def test_search_with_price_filter(self):
        engine = self._create_engine()
        engine.create_index()

        products = [
            make_product(product_id=f"P{i}", price=float(i * 50))
            for i in range(1, 6)
        ]
        embeddings = np.random.randn(5, 512).astype(np.float32)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        engine.add_embeddings(embeddings, products)

        results = engine.search(
            embeddings[0], k=10,
            filters={"min_price": 100, "max_price": 200}
        )

        for r in results:
            assert 100 <= r["price"] <= 200

    def test_search_with_category_filter(self):
        engine = self._create_engine()
        engine.create_index()

        products = [
            make_product(product_id=f"P{i}", category="Women > Dresses" if i % 2 == 0 else "Men > Shirts")
            for i in range(10)
        ]
        embeddings = np.random.randn(10, 512).astype(np.float32)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        engine.add_embeddings(embeddings, products)

        results = engine.search(
            embeddings[0], k=10,
            filters={"category": "Women"}
        )

        for r in results:
            assert "women" in r["category"].lower()

    def test_search_with_brand_filter(self):
        engine = self._create_engine()
        engine.create_index()

        products = [
            make_product(product_id=f"P{i}", brand="Nike" if i < 3 else "Adidas")
            for i in range(6)
        ]
        embeddings = np.random.randn(6, 512).astype(np.float32)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        engine.add_embeddings(embeddings, products)

        results = engine.search(embeddings[0], k=10, filters={"brand": "Nike"})

        for r in results:
            assert r["brand"] == "Nike"

    def test_is_ready_true(self):
        engine = self._create_engine()
        engine.create_index()
        embeddings = np.random.randn(1, 512).astype(np.float32)
        engine.add_embeddings(embeddings, [make_product()])

        assert engine.is_ready() is True

    def test_is_ready_false_no_index(self):
        engine = self._create_engine()
        assert engine.is_ready() is False

    def test_is_ready_false_empty_index(self):
        engine = self._create_engine()
        engine.create_index()
        assert engine.is_ready() is False

    def test_get_index_stats(self):
        engine = self._create_engine()
        engine.create_index()
        embeddings = np.random.randn(5, 512).astype(np.float32)
        engine.add_embeddings(embeddings, make_products(5))

        stats = engine.get_index_stats()

        assert stats["status"] == "loaded"
        assert stats["total_vectors"] == 5
        assert stats["dimension"] == 512
        assert stats["index_type"] == "Flat"
        assert stats["products_mapped"] == 5

    def test_get_index_stats_no_index(self):
        engine = self._create_engine()
        stats = engine.get_index_stats()
        assert stats["status"] == "not_initialized"

    def test_matches_filters_no_filters(self):
        engine = self._create_engine()
        product = make_product()
        assert engine._matches_filters(product, {}) is True

    def test_matches_filters_color(self):
        engine = self._create_engine()
        product = make_product(color="Red")

        assert engine._matches_filters(product, {"color": "Red"}) is True
        assert engine._matches_filters(product, {"color": "Blue"}) is False


# ═══════════════════════════════════════════════════════════════════
# Cache Service Tests
# ═══════════════════════════════════════════════════════════════════

class TestCacheService:
    """Tests for Redis cache service (using mock)."""

    def test_connect(self, mock_cache):
        assert mock_cache.connect() is True
        assert mock_cache.is_connected() is True

    def test_text_embedding_cache_miss(self, mock_cache):
        result = mock_cache.get_text_embedding("red dress")
        assert result is None

    def test_text_embedding_cache_hit(self, mock_cache):
        embedding = np.random.randn(512).astype(np.float32)
        mock_cache.set_text_embedding("red dress", embedding)

        result = mock_cache.get_text_embedding("red dress")
        assert result is not None
        np.testing.assert_array_equal(result, embedding)

    def test_text_embedding_case_insensitive(self, mock_cache):
        embedding = np.random.randn(512).astype(np.float32)
        mock_cache.set_text_embedding("Red Dress", embedding)

        result = mock_cache.get_text_embedding("red dress")
        assert result is not None

    def test_search_results_cache_miss(self, mock_cache):
        result = mock_cache.get_search_results("text", "query", None, 20)
        assert result is None

    def test_clear_all(self, mock_cache):
        mock_cache.set_text_embedding("test", np.zeros(512, dtype=np.float32))
        assert mock_cache.get_stats()["total_keys"] > 0

        mock_cache.clear_all()
        assert mock_cache.get_stats()["total_keys"] == 0

    def test_get_stats(self, mock_cache):
        stats = mock_cache.get_stats()
        assert stats["status"] == "connected"
        assert "total_keys" in stats


# ═══════════════════════════════════════════════════════════════════
# Search Logger Tests
# ═══════════════════════════════════════════════════════════════════

class TestSearchLogger:
    """Tests for search logging service."""

    def test_hash_image(self):
        from app.services.search_logger import SearchLogger

        image_bytes = create_test_image()
        hash1 = SearchLogger.hash_image(image_bytes)

        assert isinstance(hash1, str)
        assert len(hash1) == 16

    def test_hash_image_deterministic(self):
        from app.services.search_logger import SearchLogger

        image_bytes = create_test_image()
        hash1 = SearchLogger.hash_image(image_bytes)
        hash2 = SearchLogger.hash_image(image_bytes)

        assert hash1 == hash2

    def test_hash_image_different_for_different_images(self):
        from app.services.search_logger import SearchLogger

        img1 = create_test_image(color=(255, 0, 0))
        img2 = create_test_image(color=(0, 0, 255))

        hash1 = SearchLogger.hash_image(img1)
        hash2 = SearchLogger.hash_image(img2)

        assert hash1 != hash2

    def test_log_search_success(self, db_session):
        from app.services.search_logger import SearchLogger

        result = SearchLogger.log_search(
            db=db_session,
            query_id="test-query-123",
            query_type="text",
            query_text="red dress",
            results_count=10,
            latency_ms=150,
            top_result_ids=["id1", "id2"],
        )

        assert result is True

    def test_log_search_all_types(self, db_session):
        from app.services.search_logger import SearchLogger

        for query_type in ["image", "text", "hybrid"]:
            result = SearchLogger.log_search(
                db=db_session,
                query_id=f"test-{query_type}",
                query_type=query_type,
                query_text="test" if query_type != "image" else None,
                results_count=5,
                latency_ms=100,
            )
            assert result is True
