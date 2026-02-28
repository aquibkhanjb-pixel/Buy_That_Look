"""
Flipkart Spider - Scrapes fashion products from Flipkart.com.

Uses Playwright to load search result pages and extracts product data
from HTML cards. Also tries JSON-LD structured data when available.

Usage:
    python run_scraper.py flipkart --max-products 100
    python run_scraper.py flipkart --category "sneakers"
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


class FlipkartSpider(BaseFashionSpider):
    """
    Flipkart spider using Playwright for page rendering.

    Scrapes search result listing pages to extract product data.
    Uses structural selectors and JSON-LD for stability.
    """

    name = "flipkart"
    source_site = "flipkart"
    allowed_domains = ["flipkart.com"]

    custom_settings = {
        'DOWNLOAD_DELAY': 5,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'ROBOTSTXT_OBEY': False,
        'COOKIES_ENABLED': True,
        'HTTPERROR_ALLOWED_CODES': [403],
    }

    # Search queries for fashion categories
    SEARCH_QUERIES = {
        'men tshirts': 'Men > T-Shirts',
        'men shirts': 'Men > Shirts',
        'men jeans': 'Men > Pants',
        'men jackets': 'Men > Jackets',
        'men sneakers': 'Accessories > Sneakers',
        'running shoes men': 'Accessories > Sneakers',
        'women dresses': 'Women > Dresses',
        'women tops': 'Women > Tops',
        'women jeans': 'Women > Pants',
        'women skirts': 'Women > Skirts',
        'women heels': 'Accessories > Shoes',
        'handbags women': 'Accessories > Bags',
        'backpacks': 'Accessories > Bags',
        'sunglasses': 'Accessories > Sunglasses',
        'kurta men': 'Men > Ethnic Wear',
        'kurti women': 'Women > Ethnic Wear',
    }

    def start_requests(self):
        """Generate search page requests."""
        queries = self.SEARCH_QUERIES

        if self.category:
            cat_lower = self.category.lower()
            queries = {k: v for k, v in queries.items()
                      if cat_lower in k.lower() or cat_lower in v.lower()}
            if not queries:
                queries = {self.category: self.category}

        for query, category in queries.items():
            url = f"https://www.flipkart.com/search?q={quote_plus(query)}&marketplace=FLIPKART"
            yield scrapy.Request(
                url,
                callback=self.parse_search_results,
                meta={
                    'playwright': True,
                    'category': category,
                    'query': query,
                    'playwright_page_methods': [
                        {"method": "wait_for_timeout", "args": [3000]},
                    ],
                },
            )

    def parse_search_results(self, response: Response):
        """Parse Flipkart search results page."""
        category = response.meta.get('category', '')
        query = response.meta.get('query', '')

        if response.status == 403:
            logger.warning(f"Flipkart blocked request for '{query}' (403) - skipping")
            return

        # Try JSON-LD first (most stable)
        json_ld_items = self._extract_json_ld(response)
        if json_ld_items:
            logger.info(f"Found {len(json_ld_items)} products via JSON-LD for '{query}'")
            for item_data in json_ld_items:
                if self.max_products and self.crawler.stats.get_value('item_scraped_count', 0) >= self.max_products:
                    return
                item = self._parse_json_ld_product(item_data, category)
                if item:
                    yield item
            return

        # Fallback: parse HTML product cards
        yield from self._parse_html_cards(response, category, query)

    def _extract_json_ld(self, response: Response) -> list:
        """Extract products from JSON-LD structured data."""
        scripts = response.css('script[type="application/ld+json"]::text').getall()
        products = []
        for script_text in scripts:
            try:
                data = json.loads(script_text)
                if isinstance(data, dict):
                    if data.get('@type') == 'ItemList':
                        products.extend(data.get('itemListElement', []))
                    elif data.get('@type') == 'Product':
                        products.append(data)
                elif isinstance(data, list):
                    products.extend(data)
            except json.JSONDecodeError:
                continue
        return products

    def _parse_json_ld_product(self, product: dict, category: str) -> FashionProductItem:
        """Parse a product from JSON-LD data."""
        try:
            # JSON-LD Product structure
            if product.get('@type') == 'ListItem':
                product = product.get('item', product)

            title = product.get('name', '')
            url = product.get('url', '')
            image = product.get('image', '')
            brand_data = product.get('brand', {})
            brand = brand_data.get('name', '') if isinstance(brand_data, dict) else str(brand_data)

            # Price from offers
            offers = product.get('offers', {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = offers.get('price', 0)
            currency = offers.get('priceCurrency', 'INR')

            if not title or not url:
                return None

            if not url.startswith('http'):
                url = f"https://www.flipkart.com{url}"
            if image and not image.startswith('http'):
                image = f"https:{image}" if image.startswith('//') else f"https://www.flipkart.com{image}"

            product_id = self._extract_product_id(url)

            return FashionProductItem(
                product_id=product_id,
                source_site=self.source_site,
                title=title,
                brand=brand,
                price=float(price) if price else None,
                currency=currency,
                category=category,
                image_url=image,
                image_urls=[image] if image else [],
                product_url=url,
            )
        except Exception as e:
            logger.warning(f"Failed to parse Flipkart JSON-LD product: {e}")
            return None

    def _parse_html_cards(self, response: Response, category: str, query: str):
        """Parse product cards from HTML."""
        # Flipkart uses multiple card layouts depending on category
        # Try different card selectors

        # Layout 1: Grid cards (most common for fashion)
        cards = response.css('div[data-id]')
        if not cards:
            # Layout 2: List cards
            cards = response.css('div._1AtVbE, div._2kHMtA, div._4ddWXP')
        if not cards:
            # Layout 3: Generic product links
            cards = response.css('a[href*="/p/itm"]')

        logger.info(f"Found {len(cards)} HTML product cards on Flipkart for '{query}'")

        for card in cards:
            if self.max_products and self.crawler.stats.get_value('item_scraped_count', 0) >= self.max_products:
                return

            # Extract product link
            link = card.css('a[href*="/p/"]::attr(href)').get()
            if not link:
                link = card.css('a::attr(href)').get()
            if not link:
                link = card.attrib.get('href', '') if card.root.tag == 'a' else ''

            if not link or '/p/' not in link:
                continue

            product_url = response.urljoin(link)

            # Title - try multiple selectors
            title = (card.css('div._4rR01T::text').get() or
                    card.css('a.s1Q9rs::text').get() or
                    card.css('a.IRpwTa::text').get() or
                    card.css('div.KzDlHZ::text').get() or
                    card.css('a[title]::attr(title)').get() or
                    '')

            if not title:
                # Try getting text from the first link
                title = card.css('a::text').get() or ''

            # Brand (often first part of title on Flipkart)
            brand = card.css('div._2WkVRV::text').get() or ''

            # Price
            price_text = (card.css('div._30jeq3::text').get() or
                         card.css('div._1_WHN1::text').get() or
                         '')
            original_text = (card.css('div._3I9_wc::text').get() or
                           card.css('div._27UcVY::text').get() or
                           '')

            # Image
            image = (card.css('img._396cs4::attr(src)').get() or
                    card.css('img._2r_T1I::attr(src)').get() or
                    card.css('img::attr(src)').get() or
                    '')

            if not title.strip():
                continue

            # Clean price (remove ₹ and commas)
            price_val = self._clean_price(price_text)
            original_val = self._clean_price(original_text)

            # Fix relative URLs
            if image and not image.startswith('http'):
                image = f"https:{image}" if image.startswith('//') else response.urljoin(image)

            product_id = self._extract_product_id(product_url)

            yield FashionProductItem(
                product_id=product_id,
                source_site=self.source_site,
                title=title.strip(),
                brand=brand.strip(),
                price=price_val,
                original_price=original_val if original_val and original_val != price_val else None,
                currency='INR',
                category=category,
                image_url=image,
                image_urls=[image] if image else [],
                product_url=product_url,
            )

    def _clean_price(self, price_text: str) -> float:
        """Clean Flipkart price string to float."""
        if not price_text:
            return None
        clean = price_text.replace('₹', '').replace(',', '').replace('Rs.', '').strip()
        try:
            return float(clean)
        except ValueError:
            return None

    def _extract_product_id(self, url: str) -> str:
        """Extract product ID from Flipkart URL."""
        # Pattern: /p/itmXXXXXXXXXX
        match = re.search(r'/p/(itm[a-zA-Z0-9]+)', url)
        if match:
            return match.group(1)
        # Fallback: use last path segment
        parts = url.rstrip('/').split('/')
        return parts[-1] if parts else url[:20]

    def parse_product(self, response: Response) -> Iterator[FashionProductItem]:
        """Parse individual product page (not typically used)."""
        pass
