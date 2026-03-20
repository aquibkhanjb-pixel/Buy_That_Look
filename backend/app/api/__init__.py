"""API router configuration."""

from fastapi import APIRouter

from .endpoints import products, health, chat, tryon, trends, findlook, alerts, users, payments, wishlist, chat_history, occasion, admin

api_router = APIRouter()

api_router.include_router(health.router,    tags=["Health"])
api_router.include_router(products.router,  prefix="/products",  tags=["Products"])
api_router.include_router(chat.router,      prefix="/chat",      tags=["Chat"])
api_router.include_router(tryon.router,     prefix="/tryon",     tags=["Try-On"])
api_router.include_router(trends.router,    prefix="/trends",    tags=["Trends"])
api_router.include_router(findlook.router,  prefix="/findlook",  tags=["Find This Look"])
api_router.include_router(alerts.router,    prefix="/alerts",    tags=["Price Alerts"])
api_router.include_router(users.router,    prefix="/users",     tags=["Users"])
api_router.include_router(payments.router, prefix="/payments",  tags=["Payments"])
api_router.include_router(wishlist.router,      prefix="/wishlist",       tags=["Wishlist"])
api_router.include_router(chat_history.router, prefix="/chat/history",   tags=["Chat History"])
api_router.include_router(occasion.router,     prefix="/occasion",       tags=["Occasion Planner"])
api_router.include_router(admin.router,        prefix="/admin",          tags=["Admin"])
