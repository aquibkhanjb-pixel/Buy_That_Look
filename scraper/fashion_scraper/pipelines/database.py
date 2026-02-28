"""
Database Pipeline - Stores scraped products in PostgreSQL.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, String, Text, Numeric, Boolean, DateTime, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

Base = declarative_base()


class ScrapedProduct(Base):
    """
    SQLAlchemy model for scraped products.

    Mirrors the Product model in the backend.
    """
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(String(255), unique=True, nullable=False, index=True)
    source_site = Column(String(50), nullable=False)

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    brand = Column(String(100), nullable=True)

    price = Column(Numeric(10, 2), nullable=True)
    original_price = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="USD")

    category = Column(String(100), nullable=True)
    subcategory = Column(String(100), nullable=True)
    color = Column(String(50), nullable=True)
    size = Column(String(50), nullable=True)

    image_url = Column(Text, nullable=False)
    additional_images = Column(ARRAY(Text), default=list)
    product_url = Column(Text, nullable=False)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_scraped = Column(DateTime, default=datetime.utcnow)


class DatabasePipeline:
    """
    Pipeline for storing products in PostgreSQL.

    Handles:
    - Database connection management
    - Insert/update (upsert) logic
    - Batch commits for performance
    """

    def __init__(self, database_url: str, batch_size: int = 50):
        self.database_url = database_url
        self.batch_size = batch_size
        self.engine = None
        self.session = None
        self.items_buffer = []

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            database_url=crawler.settings.get('DATABASE_URL'),
            batch_size=crawler.settings.getint('DB_BATCH_SIZE', 50),
        )

    def open_spider(self, spider):
        """Initialize database connection when spider opens."""
        try:
            self.engine = create_engine(
                self.database_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
            )
            Session = sessionmaker(bind=self.engine)
            self.session = Session()

            # Create tables if they don't exist
            Base.metadata.create_all(self.engine)

            logger.info("Database connection established")
        except SQLAlchemyError as e:
            logger.error(f"Database connection failed: {e}")
            self.session = None

    def close_spider(self, spider):
        """Flush buffer and close connection when spider closes."""
        # Flush remaining items
        if self.items_buffer:
            self._commit_batch()

        if self.session:
            self.session.close()
        if self.engine:
            self.engine.dispose()

        logger.info("Database connection closed")

    def process_item(self, item, spider):
        """Add item to buffer and commit when batch is full."""
        if not self.session:
            logger.warning("No database connection - skipping storage")
            return item

        self.items_buffer.append(item)

        if len(self.items_buffer) >= self.batch_size:
            self._commit_batch()

        return item

    def _commit_batch(self):
        """Commit buffered items to database."""
        if not self.items_buffer:
            return

        try:
            for item in self.items_buffer:
                self._upsert_product(item)

            self.session.commit()
            logger.info(f"Committed {len(self.items_buffer)} products to database")

        except SQLAlchemyError as e:
            logger.error(f"Database commit failed: {e}")
            self.session.rollback()

        finally:
            self.items_buffer.clear()

    def _upsert_product(self, item):
        """Insert or update a product."""
        # Check if product exists
        existing = self.session.query(ScrapedProduct).filter_by(
            product_id=item['product_id']
        ).first()

        if existing:
            # Update existing product
            existing.title = item.get('title')
            existing.description = item.get('description')
            existing.brand = item.get('brand')
            existing.price = item.get('price')
            existing.original_price = item.get('original_price')
            existing.currency = item.get('currency', 'USD')
            existing.category = item.get('category')
            existing.subcategory = item.get('subcategory')
            existing.color = item.get('color')
            existing.image_url = item.get('image_url')
            existing.additional_images = item.get('additional_images', [])
            existing.product_url = item.get('product_url')
            existing.last_scraped = datetime.utcnow()
            existing.updated_at = datetime.utcnow()

            logger.debug(f"Updated: {item['product_id']}")
        else:
            # Create new product
            product = ScrapedProduct(
                product_id=item['product_id'],
                source_site=item['source_site'],
                title=item.get('title'),
                description=item.get('description'),
                brand=item.get('brand'),
                price=item.get('price'),
                original_price=item.get('original_price'),
                currency=item.get('currency', 'USD'),
                category=item.get('category'),
                subcategory=item.get('subcategory'),
                color=item.get('color'),
                image_url=item.get('image_url'),
                additional_images=item.get('additional_images', []),
                product_url=item.get('product_url'),
                last_scraped=datetime.utcnow(),
            )
            self.session.add(product)

            logger.debug(f"Inserted: {item['product_id']}")
