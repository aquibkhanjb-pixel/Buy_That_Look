"""
Base Spider - Abstract base class for all fashion spiders.

Provides common functionality for scraping fashion products.
"""

import logging
from abc import abstractmethod
from typing import Optional, Dict, Any, Iterator

import scrapy
from scrapy.http import Response

from fashion_scraper.items import FashionProductItem, FashionProductLoader

logger = logging.getLogger(__name__)


class BaseFashionSpider(scrapy.Spider):
    """
    Abstract base spider for fashion e-commerce sites.

    Subclasses must implement:
    - parse_product(): Extract product data from product page
    - get_product_urls(): Generate product URLs to scrape

    Optional overrides:
    - parse_listing(): Parse category/listing pages
    - get_start_urls(): Override to customize start URLs
    """

    # To be set by subclasses
    name: str = "base_fashion"
    source_site: str = "unknown"
    allowed_domains: list = []
    start_urls: list = []

    # Spider settings
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Allow overriding settings via CLI
        self.max_products = int(kwargs.get('max_products', 0))  # 0 = no limit
        self.category = kwargs.get('category', None)

    def start_requests(self):
        """Generate initial requests."""
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                meta={'category': self.category}
            )

    def parse(self, response: Response):
        """
        Default parse method - should be overridden by subclasses.

        Typically handles listing pages and yields requests to product pages.
        """
        yield from self.parse_listing(response)

    def parse_listing(self, response: Response) -> Iterator[scrapy.Request]:
        """
        Parse a category/listing page.

        Override this to extract product URLs from listing pages.
        """
        # Default implementation: try to find product links
        product_links = response.css('a[href*="product"]::attr(href)').getall()

        for link in product_links:
            yield response.follow(
                link,
                callback=self.parse_product,
                meta=response.meta
            )

        # Handle pagination
        next_page = response.css('a.next::attr(href)').get()
        if next_page:
            yield response.follow(
                next_page,
                callback=self.parse_listing,
                meta=response.meta
            )

    @abstractmethod
    def parse_product(self, response: Response) -> Iterator[FashionProductItem]:
        """
        Parse a product page and extract product data.

        Must be implemented by subclasses.

        Args:
            response: Scrapy response object

        Yields:
            FashionProductItem with product data
        """
        raise NotImplementedError("Subclasses must implement parse_product()")

    def create_item_loader(self, response: Response) -> FashionProductLoader:
        """Create and return a pre-configured item loader."""
        loader = FashionProductLoader(response=response)
        loader.add_value('source_site', self.source_site)
        loader.add_value('product_url', response.url)
        return loader

    def extract_price(self, response: Response, selectors: list) -> Optional[str]:
        """
        Try multiple selectors to extract price.

        Args:
            response: Scrapy response
            selectors: List of CSS selectors to try

        Returns:
            Price string or None
        """
        for selector in selectors:
            price = response.css(selector).get()
            if price:
                return price.strip()
        return None

    def extract_images(self, response: Response, selectors: list) -> list:
        """
        Extract all product images using multiple selectors.

        Args:
            response: Scrapy response
            selectors: List of CSS selectors to try

        Returns:
            List of image URLs
        """
        images = []
        for selector in selectors:
            urls = response.css(selector).getall()
            images.extend(urls)

        # Remove duplicates while preserving order
        seen = set()
        unique_images = []
        for url in images:
            if url and url not in seen:
                seen.add(url)
                # Ensure absolute URL
                if url.startswith('//'):
                    url = 'https:' + url
                elif url.startswith('/'):
                    url = response.urljoin(url)
                unique_images.append(url)

        return unique_images

    def handle_error(self, failure):
        """Handle request errors."""
        logger.error(f"Request failed: {failure.request.url}")
        logger.error(f"Error: {failure.value}")
