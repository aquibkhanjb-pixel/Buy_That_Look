"""
Tests for Pydantic schemas and SQLAlchemy models.

Tests:
- Schema validation (required fields, type coercion, constraints)
- Schema serialization
- Model to_dict methods
"""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError


# ═══════════════════════════════════════════════════════════════════
# Product Schemas
# ═══════════════════════════════════════════════════════════════════

class TestProductSchemas:
    """Tests for product Pydantic schemas."""

    def test_product_response_valid(self):
        from app.schemas.product import ProductResponse

        product = ProductResponse(
            id="test-id",
            product_id="PROD_001",
            title="Red Summer Dress",
            price=49.99,
            image_url="https://example.com/img.jpg",
            product_url="https://example.com/product",
            source_site="amazon",
            similarity=0.95,
        )

        assert product.title == "Red Summer Dress"
        assert product.similarity == 0.95
        assert product.currency == "USD"  # default

    def test_product_response_similarity_bounds(self):
        from app.schemas.product import ProductResponse

        # Valid boundary values
        ProductResponse(
            id="1", product_id="P1", title="T", image_url="u",
            product_url="u", source_site="s", similarity=0.0,
        )
        ProductResponse(
            id="1", product_id="P1", title="T", image_url="u",
            product_url="u", source_site="s", similarity=1.0,
        )

        # Invalid
        with pytest.raises(ValidationError):
            ProductResponse(
                id="1", product_id="P1", title="T", image_url="u",
                product_url="u", source_site="s", similarity=1.5,
            )

        with pytest.raises(ValidationError):
            ProductResponse(
                id="1", product_id="P1", title="T", image_url="u",
                product_url="u", source_site="s", similarity=-0.1,
            )

    def test_product_response_optional_fields(self):
        from app.schemas.product import ProductResponse

        product = ProductResponse(
            id="1", product_id="P1", title="Test",
            image_url="u", product_url="u", source_site="s",
            similarity=0.5,
        )

        assert product.description is None
        assert product.brand is None
        assert product.price is None
        assert product.category is None

    def test_product_detail_all_fields(self):
        from app.schemas.product import ProductDetail

        product = ProductDetail(
            id="test-id",
            product_id="PROD_001",
            title="Test Product",
            description="A test product",
            brand="TestBrand",
            price=49.99,
            original_price=79.99,
            currency="USD",
            category="Women > Dresses",
            subcategory="Dresses",
            color="Red",
            size="M",
            image_url="https://example.com/img.jpg",
            additional_images=["img1.jpg", "img2.jpg"],
            product_url="https://example.com/product",
            source_site="amazon",
            is_active=True,
            created_at=datetime.now(),
        )

        assert product.additional_images == ["img1.jpg", "img2.jpg"]
        assert product.is_active is True

    def test_product_list_schema(self):
        from app.schemas.product import ProductList, ProductDetail

        items = [
            ProductDetail(
                id=str(i), product_id=f"P{i}", title=f"Product {i}",
                image_url="u", product_url="u", source_site="s",
            )
            for i in range(3)
        ]

        product_list = ProductList(
            items=items,
            total=10,
            page=1,
            page_size=3,
            has_more=True,
        )

        assert len(product_list.items) == 3
        assert product_list.total == 10
        assert product_list.has_more is True


# ═══════════════════════════════════════════════════════════════════
# Search Schemas
# ═══════════════════════════════════════════════════════════════════

class TestSearchSchemas:
    """Tests for search-related Pydantic schemas."""

    def test_search_filters(self):
        from app.schemas.search import SearchFilters

        filters = SearchFilters(
            min_price=10.0,
            max_price=100.0,
            category="Women",
            brand="Nike",
        )

        assert filters.min_price == 10.0
        assert filters.max_price == 100.0

    def test_search_filters_all_optional(self):
        from app.schemas.search import SearchFilters

        filters = SearchFilters()

        assert filters.min_price is None
        assert filters.max_price is None
        assert filters.category is None
        assert filters.brand is None
        assert filters.color is None

    def test_search_filters_price_validation(self):
        from app.schemas.search import SearchFilters

        # Negative price should fail
        with pytest.raises(ValidationError):
            SearchFilters(min_price=-10)

    def test_text_search_request_valid(self):
        from app.schemas.search import TextSearchRequest

        request = TextSearchRequest(
            query="blue denim jacket",
            k=20,
        )

        assert request.query == "blue denim jacket"
        assert request.k == 20
        assert request.filters is None

    def test_text_search_request_defaults(self):
        from app.schemas.search import TextSearchRequest

        request = TextSearchRequest(query="test query")
        assert request.k == 20
        assert request.filters is None

    def test_text_search_request_query_length(self):
        from app.schemas.search import TextSearchRequest

        # Too short
        with pytest.raises(ValidationError):
            TextSearchRequest(query="ab")

        # Too long
        with pytest.raises(ValidationError):
            TextSearchRequest(query="a" * 501)

    def test_text_search_request_k_bounds(self):
        from app.schemas.search import TextSearchRequest

        with pytest.raises(ValidationError):
            TextSearchRequest(query="test query", k=0)

        with pytest.raises(ValidationError):
            TextSearchRequest(query="test query", k=101)

    def test_hybrid_search_request(self):
        from app.schemas.search import HybridSearchRequest

        request = HybridSearchRequest(
            query="find similar in blue",
            alpha=0.7,
            k=10,
        )

        assert request.alpha == 0.7
        assert request.k == 10

    def test_hybrid_search_request_alpha_bounds(self):
        from app.schemas.search import HybridSearchRequest

        # Valid boundaries
        HybridSearchRequest(query="test query", alpha=0.0)
        HybridSearchRequest(query="test query", alpha=1.0)

        # Invalid
        with pytest.raises(ValidationError):
            HybridSearchRequest(query="test query", alpha=-0.1)

        with pytest.raises(ValidationError):
            HybridSearchRequest(query="test query", alpha=1.1)

    def test_search_response(self):
        from app.schemas.search import SearchResponse, SearchResult

        results = [
            SearchResult(
                id="1", product_id="P1", title="Test",
                image_url="u", product_url="u", source_site="s",
                similarity=0.95,
            )
        ]

        response = SearchResponse(
            query_id="q1",
            results=results,
            latency_ms=150,
            total_results=1,
        )

        assert response.query_id == "q1"
        assert response.latency_ms == 150
        assert len(response.results) == 1
        assert response.model_version == "clip-vit-b32-v1"

    def test_search_response_empty(self):
        from app.schemas.search import SearchResponse

        response = SearchResponse(
            query_id="q1",
            results=[],
            latency_ms=5,
            total_results=0,
        )

        assert response.total_results == 0
        assert response.results == []


# ═══════════════════════════════════════════════════════════════════
# SQLAlchemy Model Tests
# ═══════════════════════════════════════════════════════════════════

class TestProductModel:
    """Tests for Product SQLAlchemy model."""

    def test_product_to_dict(self, db_session):
        from app.models.product import Product

        product = Product(
            product_id="TEST_001",
            source_site="test",
            title="Test Product",
            brand="TestBrand",
            price=49.99,
            category="Women > Dresses",
            image_url="https://example.com/img.jpg",
            product_url="https://example.com/product",
        )

        db_session.add(product)
        db_session.commit()
        db_session.refresh(product)

        d = product.to_dict()

        assert d["product_id"] == "TEST_001"
        assert d["title"] == "Test Product"
        assert d["brand"] == "TestBrand"
        assert d["price"] == 49.99
        assert d["source_site"] == "test"
        assert d["is_active"] is True

    def test_product_defaults(self, db_session):
        from app.models.product import Product

        product = Product(
            product_id="TEST_002",
            source_site="test",
            title="Minimal Product",
            image_url="https://example.com/img.jpg",
            product_url="https://example.com/product",
        )

        db_session.add(product)
        db_session.commit()
        db_session.refresh(product)

        assert product.currency == "USD"
        assert product.is_active is True
        assert product.description is None
        assert product.brand is None

    def test_product_unique_product_id(self, db_session):
        from app.models.product import Product
        from sqlalchemy.exc import IntegrityError

        p1 = Product(
            product_id="UNIQUE_001", source_site="test",
            title="Product 1", image_url="u", product_url="u",
        )
        p2 = Product(
            product_id="UNIQUE_001", source_site="test",
            title="Product 2", image_url="u", product_url="u",
        )

        db_session.add(p1)
        db_session.commit()

        db_session.add(p2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestCategoryModel:
    """Tests for Category SQLAlchemy model."""

    def test_category_to_dict(self, db_session):
        from app.models.category import Category

        category = Category(
            name="Women",
            level=0,
            path="Women",
        )

        db_session.add(category)
        db_session.commit()
        db_session.refresh(category)

        d = category.to_dict()
        assert d["name"] == "Women"
        assert d["level"] == 0

    def test_category_unique_name(self, db_session):
        from app.models.category import Category
        from sqlalchemy.exc import IntegrityError

        c1 = Category(name="Unique", level=0)
        c2 = Category(name="Unique", level=0)

        db_session.add(c1)
        db_session.commit()

        db_session.add(c2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestSearchLogModel:
    """Tests for SearchLog SQLAlchemy model."""

    def test_search_log_to_dict(self, db_session):
        from app.models.search_log import SearchLog

        log = SearchLog(
            session_id="session-123",
            query_type="text",
            query_text="red dress",
            results_count=10,
            latency_ms=150,
        )

        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        d = log.to_dict()
        assert d["query_type"] == "text"
        assert d["query_text"] == "red dress"
        assert d["results_count"] == 10
        assert d["latency_ms"] == 150
        assert d["created_at"] is not None
