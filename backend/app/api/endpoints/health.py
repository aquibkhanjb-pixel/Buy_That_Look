"""Health check endpoints for monitoring."""

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check():
    """Basic health check — returns service status and version."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check.
    Since all data is fetched live from Serper/Gemini, readiness == liveness.
    """
    return {
        "status": "ready",
        "checks": {"api": True},
    }


@router.get("/health/live")
async def liveness_check():
    """Liveness check — confirms the service process is running."""
    return {"status": "alive"}
