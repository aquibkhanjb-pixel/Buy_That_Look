"""
Integration tests for API endpoints.

Tests all REST API endpoints using FastAPI TestClient with mocked services.
"""

import io
import json
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from tests.conftest import (
    make_product,
    make_products,
    create_test_image,
    MockCLIPService,
    MockCacheService,
)


# ═══════════════════════════════════════════════════════════════════
# Health Check Endpoints
# ═══════════════════════════════════════════════════════════════════

class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "docs" in data

    def test_health_check(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_liveness_check(self, client):
        response = client.get("/api/v1/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_readiness_check(self, client):
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "redis" in data["checks"]
        assert "clip_model" in data["checks"]
        assert "faiss_index" in data["checks"]

    def test_ml_status(self, client):
        response = client.get("/api/v1/health/ml")
        assert response.status_code == 200
        data = response.json()
        assert "clip" in data
        assert "faiss" in data
        assert "cache" in data


# ═══════════════════════════════════════════════════════════════════
# Text Search Endpoint
# ═══════════════════════════════════════════════════════════════════

class TestTextSearchEndpoint:
    """Tests for POST /search/text."""

    def test_text_search_success(self, client):
        response = client.post("/api/v1/search/text", json={
            "query": "red summer dress",
            "k": 5,
        })

        assert response.status_code == 200
        data = response.json()
        assert "query_id" in data
        assert "results" in data
        assert "latency_ms" in data
        assert "total_results" in data
        assert isinstance(data["results"], list)

    def test_text_search_with_filters(self, client):
        response = client.post("/api/v1/search/text", json={
            "query": "blue denim jacket",
            "k": 10,
            "filters": {
                "min_price": 20.0,
                "max_price": 100.0,
                "category": "Men",
                "brand": "Levi's",
            },
        })

        assert response.status_code == 200
        data = response.json()
        assert data["filters_applied"] is not None

    def test_text_search_query_too_short(self, client):
        response = client.post("/api/v1/search/text", json={
            "query": "ab",
            "k": 5,
        })

        assert response.status_code == 422  # Validation error

    def test_text_search_query_too_long(self, client):
        response = client.post("/api/v1/search/text", json={
            "query": "a" * 501,
            "k": 5,
        })

        assert response.status_code == 422

    def test_text_search_k_bounds(self, client):
        # k too small
        response = client.post("/api/v1/search/text", json={
            "query": "test query",
            "k": 0,
        })
        assert response.status_code == 422

        # k too large
        response = client.post("/api/v1/search/text", json={
            "query": "test query",
            "k": 101,
        })
        assert response.status_code == 422

    def test_text_search_missing_query(self, client):
        response = client.post("/api/v1/search/text", json={
            "k": 5,
        })
        assert response.status_code == 422

    def test_text_search_default_k(self, client):
        response = client.post("/api/v1/search/text", json={
            "query": "casual sneakers",
        })
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# Image Search Endpoint
# ═══════════════════════════════════════════════════════════════════

class TestImageSearchEndpoint:
    """Tests for POST /search/image."""

    def test_image_search_success(self, client, test_image):
        response = client.post(
            "/api/v1/search/image",
            files={"image": ("test.jpg", io.BytesIO(test_image), "image/jpeg")},
            data={"k": "5"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "query_id" in data
        assert "results" in data
        assert "latency_ms" in data

    def test_image_search_with_filters(self, client, test_image):
        response = client.post(
            "/api/v1/search/image?k=10&min_price=20&max_price=100&category=Women",
            files={"image": ("test.jpg", io.BytesIO(test_image), "image/jpeg")},
        )

        assert response.status_code == 200

    def test_image_search_invalid_file_type(self, client):
        response = client.post(
            "/api/v1/search/image",
            files={"image": ("test.txt", io.BytesIO(b"not an image"), "text/plain")},
        )

        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    def test_image_search_png(self, client):
        from PIL import Image as PILImage
        buf = io.BytesIO()
        PILImage.new("RGB", (100, 100), (0, 255, 0)).save(buf, format="PNG")
        buf.seek(0)

        response = client.post(
            "/api/v1/search/image",
            files={"image": ("test.png", buf, "image/png")},
        )

        assert response.status_code == 200

    def test_image_search_missing_file(self, client):
        response = client.post("/api/v1/search/image")
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════
# Hybrid Search Endpoint
# ═══════════════════════════════════════════════════════════════════

class TestHybridSearchEndpoint:
    """Tests for POST /search/hybrid."""

    def test_hybrid_search_success(self, client, test_image):
        response = client.post(
            "/api/v1/search/hybrid",
            files={"image": ("test.jpg", io.BytesIO(test_image), "image/jpeg")},
            data={
                "query": "red summer dress",
                "alpha": "0.5",
                "k": "10",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "query_id" in data
        assert "results" in data

    def test_hybrid_search_alpha_bounds(self, client, test_image):
        # Alpha = 0 (text only)
        response = client.post(
            "/api/v1/search/hybrid",
            files={"image": ("test.jpg", io.BytesIO(test_image), "image/jpeg")},
            data={"query": "test dress", "alpha": "0.0", "k": "5"},
        )
        assert response.status_code == 200

        # Alpha = 1 (image only)
        response = client.post(
            "/api/v1/search/hybrid",
            files={"image": ("test.jpg", io.BytesIO(test_image), "image/jpeg")},
            data={"query": "test dress", "alpha": "1.0", "k": "5"},
        )
        assert response.status_code == 200

    def test_hybrid_search_missing_query(self, client, test_image):
        response = client.post(
            "/api/v1/search/hybrid",
            files={"image": ("test.jpg", io.BytesIO(test_image), "image/jpeg")},
            data={"alpha": "0.5", "k": "5"},
        )
        assert response.status_code == 422

    def test_hybrid_search_missing_image(self, client):
        response = client.post(
            "/api/v1/search/hybrid",
            data={"query": "red dress", "alpha": "0.5", "k": "5"},
        )
        assert response.status_code == 422

    def test_hybrid_search_invalid_image(self, client):
        response = client.post(
            "/api/v1/search/hybrid",
            files={"image": ("test.txt", io.BytesIO(b"not image"), "text/plain")},
            data={"query": "red dress", "alpha": "0.5"},
        )
        assert response.status_code == 400


# ═══════════════════════════════════════════════════════════════════
# Search Stats Endpoint
# ═══════════════════════════════════════════════════════════════════

class TestSearchStatsEndpoint:
    """Tests for GET /search/stats."""

    def test_get_stats(self, client):
        response = client.get("/api/v1/search/stats")

        assert response.status_code == 200
        data = response.json()
        assert "search_engine" in data
        assert "cache" in data


# ═══════════════════════════════════════════════════════════════════
# Products Endpoints
# ═══════════════════════════════════════════════════════════════════

class TestProductEndpoints:
    """Tests for product CRUD endpoints."""

    def test_list_products_empty(self, client):
        response = client.get("/api/v1/products/")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_products_pagination(self, client):
        response = client.get("/api/v1/products/?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert "page" in data
        assert "page_size" in data
        assert "has_more" in data

    def test_list_products_invalid_page(self, client):
        response = client.get("/api/v1/products/?page=0")
        assert response.status_code == 422

    def test_list_products_with_filters(self, client):
        response = client.get("/api/v1/products/?category=Women&brand=Nike&min_price=10&max_price=100")
        assert response.status_code == 200

    def test_get_product_not_found(self, client):
        response = client.get("/api/v1/products/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_get_similar_products_not_in_index(self, client):
        response = client.get("/api/v1/products/00000000-0000-0000-0000-000000000000/similar")
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
