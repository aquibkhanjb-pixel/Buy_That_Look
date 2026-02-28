"""
Generic Fashion Spider - Configurable spider for any e-commerce site.

This spider can be configured via command line or config file to scrape
any fashion e-commerce site by specifying CSS selectors.

Usage:
    scrapy crawl generic -a config=configs/mysite.json
    scrapy crawl generic -a url=https://example.com/products -a title_selector=".product-title"
"""

import json
import logging
from pathlib import Path
from typing import Iterator, Dict, Any, Optional

import scrapy
from scrapy.http import Response

from fashion_scraper.items import FashionProductItem, FashionProductLoader
from fashion_scraper.spiders.base import BaseFashionSpider

logger = logging.getLogger(__name__)


# Default selectors (common patterns)
DEFAULT_SELECTORS = {
    'title': [
        'h1.product-title::text',
        'h1.product-name::text',
        '[data-testid="product-title"]::text',
        '.pdp-title::text',
        '#productTitle::text',
    ],
    'price': [
        '.product-price::text',
        '.price-current::text',
        '[data-testid="price"]::text',
        '.pdp-price::text',
        '#priceblock_ourprice::text',
    ],
    'original_price': [
        '.price-original::text',
        '.price-was::text',
        '.list-price::text',
    ],
    'description': [
        '.product-description::text',
        '.pdp-description::text',
        '#productDescription::text',
        'meta[name="description"]::attr(content)',
    ],
    'brand': [
        '.product-brand::text',
        '.brand-name::text',
        '[data-testid="brand"]::text',
        '#bylineInfo::text',
    ],
    'category': [
        '.breadcrumb li:last-child::text',
        '.product-category::text',
        '[data-testid="breadcrumb"]::text',
    ],
    'image': [
        '.product-image img::attr(src)',
        '.pdp-image img::attr(src)',
        '#main-image::attr(src)',
        'meta[property="og:image"]::attr(content)',
    ],
    'images': [
        '.product-gallery img::attr(src)',
        '.thumbnail-images img::attr(src)',
        '[data-testid="gallery"] img::attr(src)',
    ],
    'product_links': [
        '.product-card a::attr(href)',
        '.product-item a::attr(href)',
        '[data-testid="product-link"]::attr(href)',
    ],
    'next_page': [
        'a.next-page::attr(href)',
        '.pagination-next::attr(href)',
        '[data-testid="next-page"]::attr(href)',
    ],
}


class GenericFashionSpider(BaseFashionSpider):
    """
    Generic spider that can be configured for any site.

    Configuration can be provided via:
    1. JSON config file: -a config=path/to/config.json
    2. Command line arguments: -a title_selector=".title"
    """

    name = "generic"
    source_site = "generic"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Load configuration
        self.config = self._load_config(kwargs)
        self.selectors = self._merge_selectors(kwargs)

        # Override start URLs if provided
        if kwargs.get('url'):
            self.start_urls = [kwargs['url']]
        elif self.config.get('start_urls'):
            self.start_urls = self.config['start_urls']

        # Set source site
        if kwargs.get('source_site'):
            self.source_site = kwargs['source_site']
        elif self.config.get('source_site'):
            self.source_site = self.config['source_site']

        # Set allowed domains
        if self.config.get('allowed_domains'):
            self.allowed_domains = self.config['allowed_domains']

        logger.info(f"Configured for: {self.source_site}")
        logger.info(f"Start URLs: {self.start_urls}")

    def _load_config(self, kwargs) -> Dict[str, Any]:
        """Load configuration from file if specified."""
        config_path = kwargs.get('config')
        if config_path:
            try:
                with open(config_path) as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load config: {e}")
        return {}

    def _merge_selectors(self, kwargs) -> Dict[str, list]:
        """Merge default selectors with config and CLI overrides."""
        selectors = DEFAULT_SELECTORS.copy()

        # Override from config file
        if self.config.get('selectors'):
            for key, value in self.config['selectors'].items():
                if isinstance(value, str):
                    selectors[key] = [value]
                else:
                    selectors[key] = value

        # Override from CLI arguments
        for key in DEFAULT_SELECTORS.keys():
            cli_selector = kwargs.get(f'{key}_selector')
            if cli_selector:
                selectors[key] = [cli_selector]

        return selectors

    def parse_listing(self, response: Response) -> Iterator[scrapy.Request]:
        """Parse listing page and follow product links."""
        # Try each product link selector
        product_links = []
        for selector in self.selectors.get('product_links', []):
            links = response.css(selector).getall()
            if links:
                product_links.extend(links)
                break

        logger.info(f"Found {len(product_links)} product links on {response.url}")

        for link in product_links:
            # Check max_products limit
            if self.max_products and self.crawler.stats.get_value('item_scraped_count', 0) >= self.max_products:
                return

            yield response.follow(
                link,
                callback=self.parse_product,
                meta=response.meta
            )

        # Handle pagination
        for selector in self.selectors.get('next_page', []):
            next_page = response.css(selector).get()
            if next_page:
                yield response.follow(
                    next_page,
                    callback=self.parse_listing,
                    meta=response.meta
                )
                break

    def parse_product(self, response: Response) -> Iterator[FashionProductItem]:
        """Parse product page using configured selectors."""
        loader = self.create_item_loader(response)

        # Extract product ID from URL
        product_id = self._extract_product_id(response.url)
        loader.add_value('product_id', product_id)

        # Title
        for selector in self.selectors.get('title', []):
            loader.add_css('title', selector)
            if loader.get_output_value('title'):
                break

        # Price
        for selector in self.selectors.get('price', []):
            loader.add_css('price', selector)
            if loader.get_output_value('price'):
                break

        # Original price
        for selector in self.selectors.get('original_price', []):
            loader.add_css('original_price', selector)
            if loader.get_output_value('original_price'):
                break

        # Description
        for selector in self.selectors.get('description', []):
            loader.add_css('description', selector)
            if loader.get_output_value('description'):
                break

        # Brand
        for selector in self.selectors.get('brand', []):
            loader.add_css('brand', selector)
            if loader.get_output_value('brand'):
                break

        # Category
        for selector in self.selectors.get('category', []):
            loader.add_css('category', selector)
            if loader.get_output_value('category'):
                break

        # Main image
        for selector in self.selectors.get('image', []):
            image_url = response.css(selector).get()
            if image_url:
                loader.add_value('image_url', response.urljoin(image_url))
                break

        # Additional images
        all_images = self.extract_images(response, self.selectors.get('images', []))
        if all_images:
            loader.add_value('image_urls', all_images)
            loader.add_value('additional_images', all_images[1:] if len(all_images) > 1 else [])

        item = loader.load_item()

        # Validate we got minimum required fields
        if item.get('title') and item.get('image_url'):
            yield item
        else:
            logger.warning(f"Incomplete product data for: {response.url}")

    def _extract_product_id(self, url: str) -> str:
        """Extract product ID from URL."""
        import re
        from urllib.parse import urlparse, parse_qs

        # Try common patterns
        patterns = [
            r'/product/([^/]+)',
            r'/p/([^/]+)',
            r'/dp/([^/]+)',
            r'/item/([^/]+)',
            r'[?&]id=([^&]+)',
            r'[?&]pid=([^&]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # Fallback: use URL path hash
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:12]
