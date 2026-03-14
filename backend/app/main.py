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

from app.api import api_router
from app.config import get_settings
from app.core.logging import setup_logging, logger
from app.services.llm_service import llm_service
from app.services.chat_service import chat_service
from app.services.tryon_service import tryon_service

settings = get_settings()

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

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    # Cleanup resources if needed


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
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
