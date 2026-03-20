"""
Fashion Recommendation System - FastAPI Application

AI-powered fashion recommendation API using Gemini and Serper web search.
"""

import os

# Load .env into os.environ BEFORE any langsmith/langgraph imports
# so LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY are available immediately.
from dotenv import load_dotenv
load_dotenv(override=False)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.api import api_router
from app.config import get_settings
from app.core.logging import setup_logging, logger
from app.core.alerts_db import init_alerts_db
from app.core.scheduler import start_scheduler, stop_scheduler
from app.db.database import create_tables
from app.services.llm_service import llm_service
from app.services.chat_service import chat_service
from app.services.tryon_service import tryon_service

settings = get_settings()

# Sentry — initialise before anything else so all errors are captured
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.2,   # 20% of requests for performance tracing
        send_default_pii=False,
    )

# Rate limiter instance (shared across endpoints)
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Runs startup and shutdown tasks.
    """
    # Startup
    setup_logging()
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # LangSmith tracing — env vars already loaded by load_dotenv() at module level
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true" and os.environ.get("LANGCHAIN_API_KEY"):
        logger.info(f"LangSmith tracing enabled → project: '{os.environ.get('LANGCHAIN_PROJECT', 'default')}'")
    else:
        logger.info("LangSmith tracing disabled (set LANGCHAIN_API_KEY + LANGCHAIN_TRACING_V2=true to enable)")

    # Initialise LLM service
    logger.info("Initialising LLM service...")
    llm_service.initialize(settings.gemini_api_key)
    if llm_service.is_enabled:
        logger.info("LLM service ready (Gemini vision + chat enabled)")
    else:
        logger.warning("LLM service disabled — chat works but without AI features")

    # Initialise Chat service (LangGraph)
    chat_service.initialize()
    tryon_service.initialize(settings.hf_token)
    logger.info("Chat service (LangGraph) initialised")

    # Create users / subscriptions tables
    try:
        create_tables()
        logger.info("User/subscription tables ready (PostgreSQL)")
    except Exception as e:
        logger.warning(f"User tables unavailable: {e}")

    # Price alerts — ensure table exists, then start daily cron
    try:
        init_alerts_db()
        logger.info("Price alerts table ready (PostgreSQL)")
        start_scheduler()
    except Exception as e:
        logger.warning(f"Price alerts DB/scheduler unavailable: {e} — alerts feature disabled")

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    ## Fashion Recommendation System API

    A hybrid multi-modal fashion recommendation system that enables users to
    discover visually similar fashion products using:

    - **AI Chat Assistant**: Conversational product discovery with Gemini
    - **Web Search**: Real-time product search via Serper.dev
    - **Visual Try-On**: Upload your photo to try on garments
    - **Trend Discovery**: Curated weekly fashion trends

    ### Features
    - Conversational AI powered by Gemini + LangGraph
    - Real-time web product search via Serper.dev
    - Image understanding with Gemini Vision
    - Rate limiting to prevent abuse
    - Direct purchase links to e-commerce platforms (Myntra, Ajio, Amazon, Flipkart)
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Attach rate limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
# In production, set CORS_ORIGINS env var to comma-separated list of allowed origins
_cors_origins = settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins + ["https://fashionfinder-bice.vercel.app"],
    allow_origin_regex=r"https://.*\.vercel\.app",  # allow all Vercel preview URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint returning API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
