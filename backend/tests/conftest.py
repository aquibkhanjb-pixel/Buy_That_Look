"""
Shared test fixtures for Fashion Recommendation System.

Provides:
- Test database with SQLite (no PostgreSQL needed for tests)
- FastAPI test client
- Mock CLIP service (returns deterministic embeddings)
- Mock search engine with sample data
- Sample product factories
"""

import uuid
import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment before importing app modules
os.environ["DATABASE_URL"] = "sqlite:///test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["DEBUG"] = "true"

from app.core.database import Base, get_db
from app.config import Settings


# ─── Test Database ────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    # Create tables
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


def override_get_db():
    """Override database dependency for tests."""
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ─── Mock CLIP Service ────────────────────────────────────────────

class MockCLIPService:
    """Mock CLIP service that returns deterministic embeddings."""

    def __init__(self):
        self.device = "cpu"
        self.model_name = "ViT-B/32"
        self.embedding_dim = 512
        self.model = True  # Simulate loaded model

    def is_loaded(self) -> bool:
        return True

    def load_model(self) -> bool:
        return True

    def encode_image(self, image) -> np.ndarray:
        """Return a deterministic embedding based on image bytes hash."""
        if isinstance(image, bytes):
            seed = hash(image) % 2**31
        else:
            seed = 42
        rng = np.random.RandomState(seed)
        embedding = rng.randn(512).astype(np.float32)
        return embedding / np.linalg.norm(embedding)

    def encode_text(self, text: str) -> np.ndarray:
        """Return a deterministic embedding based on text hash."""
        seed = hash(text) % 2**31
        rng = np.random.RandomState(seed)
        embedding = rng.randn(512).astype(np.float32)
        return embedding / np.linalg.norm(embedding)

    def encode_images_batch(self, images, batch_size=32) -> np.ndarray:
        return np.array([self.encode_image(img) for img in images], dtype=np.float32)

    def encode_texts_batch(self, texts, batch_size=32) -> np.ndarray:
        return np.array([self.encode_text(t) for t in texts], dtype=np.float32)

    def compute_hybrid_embedding(self, image_emb, text_emb, alpha=0.5) -> np.ndarray:
        hybrid = alpha * image_emb + (1 - alpha) * text_emb
        norm = np.linalg.norm(hybrid)
        if norm > 0:
            hybrid = hybrid / norm
        return hybrid.astype(np.float32)

    def compute_similarity(self, query, targets) -> np.ndarray:
        if query.ndim == 1:
            query = query.reshape(1, -1)
        return np.dot(targets, query.T).squeeze()


@pytest.fixture
def mock_clip():
    """Provide a mock CLIP service."""
    return MockCLIPService()


# ─── Mock Cache Service ──────────────────────────────────────────

class MockCacheService:
    """In-memory mock cache for tests."""

    def __init__(self):
        self._store = {}
        self.connected = True

    def connect(self) -> bool:
        self.connected = True
        return True

    def is_connected(self) -> bool:
        return self.connected

    def get_text_embedding(self, query):
        key = f"emb:{query.strip().lower()}"
        return self._store.get(key)

    def set_text_embedding(self, query, embedding):
        key = f"emb:{query.strip().lower()}"
        self._store[key] = embedding
        return True

    def get_search_results(self, *args):
        return None

    def set_search_results(self, *args):
        return True

    def clear_all(self):
        self._store.clear()
        return True

    def get_stats(self):
        return {"status": "connected", "total_keys": len(self._store)}


@pytest.fixture
def mock_cache():
    """Provide a mock cache service."""
    return MockCacheService()


# ─── Test Client ──────────────────────────────────────────────────

@pytest.fixture
def client(mock_clip):
    """Create a FastAPI test client with mocked dependencies."""
    with patch("app.services.clip_service.clip_service", mock_clip), \
         patch("app.services.search_engine.clip_service", mock_clip), \
         patch("app.api.endpoints.search.cache_service", MockCacheService()), \
         patch("app.api.endpoints.search.search_logger") as mock_logger, \
         patch("app.api.endpoints.health.cache_service", MockCacheService()):

        mock_logger.log_search.return_value = True
        mock_logger.hash_image.return_value = "abc123"

        from app.main import app
        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as c:
            yield c

        app.dependency_overrides.clear()


# ─── Sample Data Factories ───────────────────────────────────────

def make_product(**overrides) -> dict:
    """Create a sample product dict."""
    defaults = {
        "id": str(uuid.uuid4()),
        "product_id": f"PROD_{uuid.uuid4().hex[:8]}",
        "title": "Test Fashion Product",
        "description": "A beautiful test product for testing.",
        "brand": "TestBrand",
        "price": 49.99,
        "original_price": 79.99,
        "currency": "USD",
        "category": "Women > Dresses",
        "subcategory": "Dresses",
        "color": "Red",
        "image_url": "https://example.com/image.jpg",
        "additional_images": [],
        "product_url": "https://example.com/product/123",
        "source_site": "test_store",
        "similarity": 0.95,
    }
    defaults.update(overrides)
    return defaults


def make_products(n: int = 5) -> list:
    """Create a list of sample products."""
    return [
        make_product(
            product_id=f"PROD_{i:05d}",
            title=f"Test Product {i}",
            price=round(19.99 + i * 10, 2),
            category=["Women > Dresses", "Men > Shirts", "Accessories > Bags"][i % 3],
            brand=["Nike", "Adidas", "Zara"][i % 3],
            color=["Red", "Blue", "Black", "White", "Green"][i % 5],
        )
        for i in range(n)
    ]


@pytest.fixture
def sample_products():
    """Provide a list of sample products."""
    return make_products(10)


def create_test_image(width=100, height=100, color=(255, 0, 0)) -> bytes:
    """Create a test JPEG image."""
    img = Image.new("RGB", (width, height), color)
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def test_image():
    """Provide test image bytes."""
    return create_test_image()


@pytest.fixture
def test_image_file():
    """Provide a test image as a file-like tuple for upload."""
    image_bytes = create_test_image()
    return ("image", ("test.jpg", BytesIO(image_bytes), "image/jpeg"))
