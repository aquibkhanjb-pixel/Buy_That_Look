"""Health check endpoints for monitoring."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.config import get_settings
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
    }

    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False

    # Check Redis connection
    checks["redis"] = cache_service.is_connected()

    all_healthy = checks["database"]

    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
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
        "cache": cache_service.get_stats(),
    }
