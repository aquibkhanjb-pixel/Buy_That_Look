"""API router configuration."""

from fastapi import APIRouter

from .endpoints import products, health, chat, tryon, trends

api_router = APIRouter()

api_router.include_router(health.router,    tags=["Health"])
api_router.include_router(products.router,  prefix="/products", tags=["Products"])
api_router.include_router(chat.router,      prefix="/chat",     tags=["Chat"])
api_router.include_router(tryon.router,     prefix="/tryon",    tags=["Try-On"])
api_router.include_router(trends.router,    prefix="/trends",   tags=["Trends"])
