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
    # Set CORS_ORIGINS in env as comma-separated URLs, e.g.:
    # CORS_ORIGINS=https://your-app.vercel.app,http://localhost:3000
    cors_origins: list[str] = ["http://localhost:3000", "https://*.vercel.app"]

    # Rate Limiting
    rate_limit_per_minute: int = 30

    # Search defaults
    default_search_k: int = 20
    max_search_k: int = 100

    # LLM / Generative AI
    gemini_api_key: str = ""

    # Serper.dev — Google Shopping API for real product results in web search
    serper_api_key: str = ""

    # HuggingFace — Virtual Try-On (IDM-VTON Space)
    hf_token: str = ""

    # Auth — JWT (issued to NextAuth after Google login)
    jwt_secret: str = ""

    # Razorpay — subscription payments (₹99/mo, Card + UPI + Netbanking)
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_plan_id: str = ""         # plan_xxxx for ₹99/mo plan
    razorpay_webhook_secret: str = ""
    frontend_url: str = "http://localhost:3000"

    # Email — Resend.com (price drop alerts)
    resend_api_key: str = ""
    resend_from_email: str = "alerts@fashionai.app"

    # LangSmith Observability
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "fashion-recommendation"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # Cron job secret (used to authenticate cron-job.org price check requests)
    cron_secret: str = ""

    # Admin — comma-separated emails that get is_admin=True on login
    # e.g. ADMIN_EMAILS=email1@gmail.com,email2@gmail.com
    admin_emails: str = ""

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip() for e in self.admin_emails.split(',') if e.strip()]

    # Sentry error monitoring
    sentry_dsn: str = ""


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
