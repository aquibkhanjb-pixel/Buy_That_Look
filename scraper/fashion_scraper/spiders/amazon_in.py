"""
Amazon India Spider - Scrapes fashion products from Amazon.in.

Uses Playwright for page rendering with conservative rate limiting.
Scrapes listing/search result pages only (not individual product pages)
to minimize anti-bot detection risk.

Usage:
    python run_scraper.py amazon_india --max-products 100
    python run_scraper.py amazon_india --category "sneakers"
"""

import json
import re
import logging
from typing import Iterator
from urllib.parse import quote_plus

import scrapy
from scrapy.http import Response

from fashion_scraper.items import FashionProductItem
from fashion_scraper.spiders.base import BaseFashionSpider

logger = logging.getLogger(__name__)


class AmazonIndiaSpider(BaseFashionSpider):
    """
    Amazon India spider with conservative rate limiting.

    Scrapes search result pages only to extract product cards with
    title, price, image, and product URL. Individual product pages
    are NOT visited to reduce detection risk.
    """

    name = "amazon_india"
    source_site = "amazon_india"
    allowed_domains = ["amazon.in"]

    custom_settings = {
        'DOWNLOAD_DELAY': 5,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'RANDOMIZE_DOWNLOAD_DELAY': True,
        'ROBOTSTXT_OBEY': False,
        'COOKIES_ENABLED': True,
    }

    # Search queries for fashion categories
    SEARCH_QUERIES = {
        'men t-shirts': 'Men > T-Shirts',
        'men formal shirts': 'Men > Shirts',
        'men jeans': 'Men > Pants',
        'men jackets': 'Men > Jackets',
        'men sneakers casual shoes': 'Accessories > Sneakers',
        'running shoes men': 'Accessories > Sneakers',
        'women dresses western': 'Women > Dresses',
        'women tops tshirts': 'Women > Tops',
        'women jeans': 'Women > Pants',
        'women skirts': 'Women > Skirts',
        'women heels sandals': 'Accessories > Shoes',
        'handbags for women': 'Accessories > Bags',
        'sunglasses for men women': 'Accessories > Sunglasses',
        'kurta for men': 'Men > Ethnic Wear',
        'kurti for women': 'Women > Ethnic Wear',
    }

    def start_requests(self):
        """Generate search page requests with Playwright."""
        queries = self.SEARCH_QUERIES

        if self.category:
            cat_lower = self.category.lower()
            queries = {k: v for k, v in queries.items()
                      if cat_lower in k.lower() or cat_lower in v.lower()}
            if not queries:
                queries = {self.category: self.category}

        for query, category in queries.items():
            url = f"https://www.amazon.in/s?k={quote_plus(query)}&i=apparel"
            yield scrapy.Request(
                url,
                callback=self.parse_search_results,
                meta={
                    'playwright': True,
                    'category': category,
                    'query': query,
                    'playwright_page_methods': [
                        {"method": "wait_for_timeout", "args": [4000]},
                    ],
                },
                errback=self.handle_error,
            )

    def parse_search_results(self, response: Response):
        """Parse Amazon search results page."""
        category = response.meta.get('category', '')
        query = response.meta.get('query', '')

        # Check for CAPTCHA
        if self._is_captcha_page(response):
            logger.warning(f"CAPTCHA detected on Amazon for '{query}' - skipping")
            return

        # Find product cards
        cards = response.css('div[data-component-type="s-search-result"]')
        if not cards:
            # Try alternate selectors
            cards = response.css('div.s-result-item[data-asin]')

        logger.info(f"Found {len(cards)} product cards on Amazon for '{query}'")

        for card in cards:
            if self.max_products and self.crawler.stats.get_value('item_scraped_count', 0) >= self.max_products:
                return

            item = self._parse_search_card(card, response, category)
            if item:
                yield item

    def _is_captcha_page(self, response: Response) -> bool:
        """Check if Amazon returned a CAPTCHA page."""
        captcha_indicators = [
            'captchacharacters',
            'Type the characters you see in this image',
            'Sorry, we just need to make sure',
            'api-services-support@amazon.com',
        ]
        text = response.text[:5000]  # Check first 5000 chars
        return any(indicator in text for indicator in captcha_indicators)

    def _parse_search_card(self, card, response: Response, category: str) -> FashionProductItem:
        """Parse a single Amazon search result card."""
        try:
            # ASIN (Amazon product ID)
            asin = card.attrib.get('data-asin', '')
            if not asin:
                return None

            # Skip sponsored/ad results
            if card.css('span[data-component-type="s-sponsored-label-info-icon"]'):
                return None

            # Title
            title = card.css('h2 a span::text').get()
            if not title:
                title = card.css('h2 span::text').get()
            if not title:
                return None

            # Product URL
            link = card.css('h2 a::attr(href)').get()
            if link:
                product_url = response.urljoin(link)
            else:
                product_url = f"https://www.amazon.in/dp/{asin}"

            # Price
            price_whole = card.css('span.a-price-whole::text').get()
            price_text = card.css('span.a-price span.a-offscreen::text').get()

            price_val = None
            if price_whole:
                clean = price_whole.replace(',', '').replace('.', '').strip()
                try:
                    price_val = float(clean)
                except ValueError:
                    pass
            elif price_text:
                price_val = self._clean_price(price_text)

            # Original price (strikethrough)
            original_text = card.css('span.a-text-price span.a-offscreen::text').get()
            original_val = self._clean_price(original_text) if original_text else None

            # Image
            image = card.css('img.s-image::attr(src)').get()
            if not image:
                image = card.css('img::attr(src)').get()

            # Brand (try to extract)
            brand = ''
            # Amazon sometimes has brand in a separate line
            brand_text = card.css('span.a-size-base-plus::text').get()
            if brand_text:
                brand = brand_text.strip()

            # Rating (optional)
            rating = card.css('span.a-icon-alt::text').get()

            if not image:
                return None

            return FashionProductItem(
                product_id=asin,
                source_site=self.source_site,
                title=title.strip(),
                brand=brand,
                price=price_val,
                original_price=original_val if original_val and original_val != price_val else None,
                currency='INR',
                category=category,
                image_url=image,
                image_urls=[image] if image else [],
                product_url=product_url,
                description=f"{title}. Available on Amazon India.",
            )

        except Exception as e:
            logger.warning(f"Failed to parse Amazon card: {e}")
            return None

    def _clean_price(self, price_text: str) -> float:
        """Clean Amazon price string to float."""
        if not price_text:
            return None
        clean = price_text.replace('₹', '').replace(',', '').replace('Rs.', '').strip()
        try:
            return float(clean)
        except ValueError:
            return None

    def parse_product(self, response: Response) -> Iterator[FashionProductItem]:
        """Parse individual product page (not used - listing only)."""
        pass
