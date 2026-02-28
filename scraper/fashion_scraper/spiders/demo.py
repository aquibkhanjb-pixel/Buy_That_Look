"""
Demo Spider - Uses Fake Store API for testing the scraper pipeline.

This spider is useful for:
- Testing the scraping pipeline without hitting real sites
- Development and debugging
- CI/CD testing

Usage:
    scrapy crawl demo -a max_products=50
"""

import json
import logging
from typing import Iterator

import scrapy
from scrapy.http import Response

from fashion_scraper.items import FashionProductItem, FashionProductLoader
from fashion_scraper.spiders.base import BaseFashionSpider

logger = logging.getLogger(__name__)


class DemoSpider(BaseFashionSpider):
    """
    Demo spider using Fake Store API.

    The Fake Store API provides fake e-commerce data perfect for testing.
    https://fakestoreapi.com/
    """

    name = "demo"
    source_site = "fakestore"
    allowed_domains = ["fakestoreapi.com"]
    start_urls = ["https://fakestoreapi.com/products"]

    custom_settings = {
        'DOWNLOAD_DELAY': 0.5,  # Fast since it's a test API
        'ROBOTSTXT_OBEY': False,  # API doesn't have robots.txt
    }

    # Category mapping for Fake Store API
    CATEGORY_MAP = {
        "men's clothing": "Men > Clothing",
        "women's clothing": "Women > Clothing",
        "jewelery": "Accessories > Jewelry",
        "electronics": "Electronics",
    }

    def parse(self, response: Response) -> Iterator[scrapy.Request]:
        """Parse the product list from API."""
        try:
            # Try .text first, fall back to decoding body bytes directly
            try:
                body = response.text
            except AttributeError:
                body = response.body.decode('utf-8')
            products = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return

        logger.info(f"Found {len(products)} products")

        for product in products:
            # Apply max_products limit
            if self.max_products and self.crawler.stats.get_value('item_scraped_count', 0) >= self.max_products:
                logger.info(f"Reached max_products limit: {self.max_products}")
                return

            # Filter by category if specified
            if self.category and self.category.lower() not in product.get('category', '').lower():
                continue

            # For API responses, we can parse directly
            yield self.parse_api_product(product)

    def parse_api_product(self, product: dict) -> FashionProductItem:
        """Parse product data from API response."""
        # Map category
        raw_category = product.get('category', '')
        category = self.CATEGORY_MAP.get(raw_category, raw_category)

        item = FashionProductItem(
            product_id=str(product.get('id')),
            source_site=self.source_site,
            title=product.get('title'),
            description=product.get('description'),
            price=product.get('price'),
            category=category,
            image_url=product.get('image'),
            image_urls=[product.get('image')] if product.get('image') else [],
            product_url=f"https://fakestoreapi.com/products/{product.get('id')}",
            currency='USD',
        )

        # Extract brand from title (demo: use first word)
        title = product.get('title', '')
        if title:
            words = title.split()
            if words:
                item['brand'] = words[0]

        logger.debug(f"Parsed product: {item['title'][:50]}...")
        return item

    def parse_product(self, response: Response) -> Iterator[FashionProductItem]:
        """
        Parse individual product page (not used for API, but required by base).
        """
        try:
            product = json.loads(response.text)
            yield self.parse_api_product(product)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse product: {response.url}")
