"""API router configuration."""

from fastapi import APIRouter

from .endpoints import search, products, health

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(search.router, prefix="/search", tags=["Search"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
