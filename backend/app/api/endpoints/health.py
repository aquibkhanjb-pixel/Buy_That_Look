"""Health check endpoints for monitoring."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.config import get_settings
from app.services.clip_service import clip_service
from app.services.search_engine import search_engine
from app.services.cache_service import cache_service

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check():
    """
    Basic health check endpoint.
    Returns service status and version.
    """
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/health/ready")
async def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness check including database, Redis, and ML service connectivity.
    Used by orchestrators to determine if service can accept traffic.
    """
    checks = {
        "database": False,
        "redis": False,
        "clip_model": False,
        "faiss_index": False,
    }

    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    # Check Redis connection
    checks["redis"] = cache_service.is_connected()

    # Check CLIP model
    checks["clip_model"] = clip_service.is_loaded()

    # Check FAISS index
    checks["faiss_index"] = search_engine.is_ready()

    # Service is ready if core ML components are available
    # Redis is optional (graceful degradation)
    all_healthy = checks["clip_model"] and checks["faiss_index"]

    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "search_engine_stats": search_engine.get_index_stats(),
        "cache_stats": cache_service.get_stats(),
    }


@router.get("/health/live")
async def liveness_check():
    """
    Liveness check.
    Simple check to verify the service process is running.
    """
    return {"status": "alive"}


@router.get("/health/ml")
async def ml_status():
    """
    Detailed ML service status.
    Returns information about loaded models and indices.
    """
    return {
        "clip": {
            "loaded": clip_service.is_loaded(),
            "model_name": settings.clip_model_name,
            "device": clip_service.device if clip_service.is_loaded() else None,
            "embedding_dim": clip_service.embedding_dim,
        },
        "faiss": search_engine.get_index_stats(),
        "cache": cache_service.get_stats(),
    }
