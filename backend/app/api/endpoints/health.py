"""Health check endpoints for monitoring."""

import os
from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings

router = APIRouter()
settings = get_settings()

_CRON_SECRET = os.environ.get("CRON_SECRET", "")


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


@router.post("/cron/price-check")
async def trigger_price_check(x_cron_secret: str = Header(default="")):
    """
    Called by cron-job.org daily to run price drop checks.
    Requires X-Cron-Secret header matching CRON_SECRET env var.
    """
    if _CRON_SECRET and x_cron_secret != _CRON_SECRET:
        raise HTTPException(status_code=401, detail="Invalid cron secret")
    try:
        from app.services.price_checker import run_price_checks
        import threading
        t = threading.Thread(target=run_price_checks, daemon=True)
        t.start()
        return {"status": "price check started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
