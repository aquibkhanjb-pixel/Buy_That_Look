"""
Myntra Spider - Scrapes fashion products from Myntra.com.

Myntra is a React SPA that embeds product data in JavaScript variables.
Uses Playwright to load pages, then extracts the embedded JSON data.

Usage:
    python run_scraper.py myntra --max-products 100
    python run_scraper.py myntra --category "sneakers"
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


class MyntraSpider(BaseFashionSpider):
    """
    Myntra spider using Playwright for JS rendering.

    Myntra embeds product data in <script> tags as JSON. We use Playwright
    to load the page, then extract and parse the embedded data.
    """

    name = "myntra"
    source_site = "myntra"
    allowed_domains = ["myntra.com"]

    custom_settings = {
        'DOWNLOAD_DELAY': 3,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'ROBOTSTXT_OBEY': False,
    }

    # Category URL paths mapped to our taxonomy
    CATEGORY_URLS = {
        'men-tshirts': 'Men > T-Shirts',
        'men-shirts': 'Men > Shirts',
        'men-jeans': 'Men > Pants',
        'men-jackets': 'Men > Jackets',
        'men-casual-shoes': 'Accessories > Sneakers',
        'men-sports-shoes': 'Accessories > Sneakers',
        'women-dresses': 'Women > Dresses',
        'women-tops-t-shirts': 'Women > Tops',
        'women-jeans-jeggings': 'Women > Pants',
        'women-skirts': 'Women > Skirts',
        'women-heels': 'Accessories > Shoes',
        'women-flats': 'Accessories > Shoes',
        'handbags': 'Accessories > Bags',
        'backpacks': 'Accessories > Bags',
        'sunglasses': 'Accessories > Sunglasses',
        'watches': 'Accessories > Watches',
        'kurtas-for-men': 'Men > Ethnic Wear',
        'kurtis-for-women': 'Women > Ethnic Wear',
    }

    def start_requests(self):
        """Generate requests for category listing pages."""
        categories = self.CATEGORY_URLS

        if self.category:
            cat_lower = self.category.lower()
            categories = {k: v for k, v in categories.items()
                         if cat_lower in k.lower() or cat_lower in v.lower()}
            if not categories:
                # Use as search query
                url = f"https://www.myntra.com/{quote_plus(self.category)}"
                yield scrapy.Request(
                    url,
                    callback=self.parse_listing_page,
                    meta={'playwright': True, 'category': self.category,
                          'playwright_page_methods': [
                              {"method": "wait_for_timeout", "args": [3000]},
                          ]},
                )
                return

        for url_path, category in categories.items():
            url = f"https://www.myntra.com/{url_path}"
            yield scrapy.Request(
                url,
                callback=self.parse_listing_page,
                meta={'playwright': True, 'category': category,
                      'playwright_page_methods': [
                          {"method": "wait_for_timeout", "args": [3000]},
                      ]},
            )

    def parse_listing_page(self, response: Response):
        """Parse Myntra listing page and extract product data from embedded JSON."""
        category = response.meta.get('category', '')
        page_text = response.text

        # Try to extract embedded product data from script tags
        # Myntra uses window.__myx or similar patterns
        patterns = [
            r'window\.__myx\s*=\s*(\{.*?\});\s*</script>',
            r'"searchData"\s*:\s*(\{.*?"products"\s*:\s*\[.*?\]\s*\})',
            r'"results"\s*:\s*(\{.*?"products"\s*:\s*\[.*?\]\s*\})',
        ]

        products_data = None
        for pattern in patterns:
            match = re.search(pattern, page_text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if 'searchData' in data:
                        products_data = data['searchData'].get('results', {}).get('products', [])
                    elif 'products' in data:
                        products_data = data['products']
                    if products_data:
                        break
                except json.JSONDecodeError:
                    continue

        # Try alternate: look for JSON-LD structured data
        if not products_data:
            json_ld = response.css('script[type="application/ld+json"]::text').getall()
            for ld_text in json_ld:
                try:
                    ld_data = json.loads(ld_text)
                    if isinstance(ld_data, dict) and ld_data.get('@type') == 'ItemList':
                        products_data = ld_data.get('itemListElement', [])
                        break
                except json.JSONDecodeError:
                    continue

        # If JSON extraction works
        if products_data:
            logger.info(f"Found {len(products_data)} products on Myntra ({category})")
            for product in products_data:
                if self.max_products and self.crawler.stats.get_value('item_scraped_count', 0) >= self.max_products:
                    return
                item = self._parse_json_product(product, category)
                if item:
                    yield item
            return

        # Fallback: parse HTML product cards
        logger.info("Falling back to HTML parsing for Myntra")
        yield from self._parse_html_cards(response, category)

    def _parse_json_product(self, product: dict, category: str) -> FashionProductItem:
        """Parse a product from Myntra's embedded JSON."""
        try:
            # Handle different JSON structures
            product_id = (product.get('productId') or product.get('styleId')
                         or product.get('id') or '')
            title = product.get('productName') or product.get('name') or ''
            brand = product.get('brand') or product.get('brandName') or ''

            if not product_id or not title:
                return None

            # Prices
            price = product.get('price') or product.get('discountedPrice') or 0
            original_price = product.get('mrp') or product.get('originalPrice') or 0

            if isinstance(price, str):
                price = float(price.replace(',', '').replace('Rs.', '').replace('₹', '').strip() or 0)
            if isinstance(original_price, str):
                original_price = float(original_price.replace(',', '').replace('Rs.', '').replace('₹', '').strip() or 0)

            # Image
            image_url = product.get('searchImage') or product.get('image') or ''
            if image_url and not image_url.startswith('http'):
                image_url = f"https://assets.myntassets.com/{image_url}"

            # Product URL
            landing_url = product.get('landingPageUrl') or product.get('url') or ''
            if landing_url and not landing_url.startswith('http'):
                product_url = f"https://www.myntra.com/{landing_url}"
            elif landing_url:
                product_url = landing_url
            else:
                product_url = f"https://www.myntra.com/product/{product_id}"

            # Color and other info
            color = product.get('primaryColour') or product.get('color') or ''
            description = product.get('productDescription') or product.get('description') or ''
            if not description:
                description = f"{brand} {title}. Shop on Myntra."

            return FashionProductItem(
                product_id=str(product_id),
                source_site=self.source_site,
                title=f"{brand} {title}" if brand and brand.lower() not in title.lower() else title,
                description=description,
                brand=brand,
                price=float(price) if price else None,
                original_price=float(original_price) if original_price and float(original_price) != float(price or 0) else None,
                currency='INR',
                category=category,
                color=color,
                image_url=image_url,
                image_urls=[image_url] if image_url else [],
                product_url=product_url,
            )

        except Exception as e:
            logger.warning(f"Failed to parse Myntra JSON product: {e}")
            return None

    def _parse_html_cards(self, response: Response, category: str):
        """Fallback: parse product cards from HTML."""
        # Myntra product card selectors (may change)
        cards = response.css('li.product-base')
        if not cards:
            cards = response.css('div[class*="product-productMetaInfo"]')
        if not cards:
            # Try broader selector
            cards = response.css('a[href*="/buy/"]')

        logger.info(f"Found {len(cards)} HTML product cards on Myntra")

        for card in cards:
            if self.max_products and self.crawler.stats.get_value('item_scraped_count', 0) >= self.max_products:
                return

            # Extract from card
            link = card.css('a::attr(href)').get() or card.attrib.get('href', '')
            brand = card.css('h3.product-brand::text, div[class*="brand"]::text').get()
            title = card.css('h4.product-product::text, div[class*="product"]::text').get()

            price_text = card.css('div.product-discountedPrice::text, span[class*="discounted"]::text').get()
            original_text = card.css('div.product-strike::text, span[class*="strike"]::text').get()

            image = card.css('img.img-responsive::attr(src)').get()
            if not image:
                image = card.css('img::attr(src), img::attr(data-src)').get()

            if not title and not brand:
                continue

            full_title = f"{brand} {title}" if brand and title else (title or brand or '')
            product_url = response.urljoin(link) if link else ''

            # Extract product ID from URL
            product_id = ''
            if link:
                parts = link.rstrip('/').split('/')
                product_id = parts[-1] if parts else ''

            # Parse price
            price_val = None
            if price_text:
                clean = price_text.replace('Rs.', '').replace(',', '').replace('₹', '').strip()
                try:
                    price_val = float(clean)
                except ValueError:
                    pass

            original_val = None
            if original_text:
                clean = original_text.replace('Rs.', '').replace(',', '').replace('₹', '').strip()
                try:
                    original_val = float(clean)
                except ValueError:
                    pass

            if image and not image.startswith('http'):
                image = f"https:{image}" if image.startswith('//') else response.urljoin(image)

            if product_url and (full_title or image):
                yield FashionProductItem(
                    product_id=product_id or full_title[:20].replace(' ', '_'),
                    source_site=self.source_site,
                    title=full_title,
                    brand=brand or '',
                    price=price_val,
                    original_price=original_val,
                    currency='INR',
                    category=category,
                    image_url=image or '',
                    image_urls=[image] if image else [],
                    product_url=product_url,
                )

    def parse_product(self, response: Response) -> Iterator[FashionProductItem]:
        """Parse individual product page (not typically used)."""
        pass
