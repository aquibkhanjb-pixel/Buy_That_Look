"""
ORM models: User, Subscription, WishlistItem, UserUsage.
Tables are auto-created in main.py lifespan via create_tables().
"""

import uuid

from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, Date, Float, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email              = Column(Text, unique=True, nullable=False, index=True)
    name               = Column(Text, nullable=True)
    avatar_url         = Column(Text, nullable=True)
    tier                   = Column(Text, nullable=False, default="free")   # free | premium
    razorpay_customer_id   = Column(Text, nullable=True)
    created_at             = Column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    user_id                 = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    razorpay_subscription_id = Column(Text, unique=True, nullable=False)
    plan_id                 = Column(Text, nullable=True)
    status                  = Column(Text, nullable=False)   # created | authenticated | active | halted | cancelled
    current_period_end      = Column(DateTime(timezone=True), nullable=True)
    created_at              = Column(DateTime(timezone=True), server_default=func.now())


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id   = Column(Text, nullable=False)
    title        = Column(Text, nullable=False)
    product_url  = Column(Text, nullable=False, default="")
    image_url    = Column(Text, nullable=True, default="")
    price        = Column(Float, nullable=True)
    currency     = Column(Text, nullable=True, default="INR")
    source_site  = Column(Text, nullable=True, default="")
    description  = Column(Text, nullable=True)
    brand        = Column(Text, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())


class UserUsage(Base):
    __tablename__ = "user_usage"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date            = Column(Date, nullable=False)
    chat_count      = Column(Integer, nullable=False, default=0)
    occasion_count  = Column(Integer, nullable=False, default=0)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id                   = Column(Text, primary_key=True)   # UUID string — same as conversation_id
    user_id              = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title                = Column(Text, nullable=False, default="New conversation")
    user_preferences_json = Column(Text, nullable=True)      # JSON: latest user_preferences dict
    created_at           = Column(DateTime(timezone=True), server_default=func.now())
    updated_at           = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    session_id    = Column(Text, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role          = Column(Text, nullable=False)             # 'user' | 'assistant'
    content       = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)              # JSON: {products, web_results, options}
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
