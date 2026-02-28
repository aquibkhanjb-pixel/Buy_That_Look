"""
Application configuration using pydantic-settings.
Loads settings from environment variables and .env file.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Fashion Recommendation API"
    app_version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "postgresql://user:password@localhost:5432/fashiondb"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # ML Model
    clip_model_name: str = "ViT-B/32"
    model_cache_dir: str = "./models"

    # FAISS
    faiss_index_path: str = "./data/indices/fashion_products.index"

    # Storage
    image_storage_path: str = "./data/images"
    max_upload_size: int = 10 * 1024 * 1024  # 10MB

    # API Settings
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Rate Limiting
    rate_limit_per_minute: int = 30

    # Search defaults
    default_search_k: int = 20
    max_search_k: int = 100


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
