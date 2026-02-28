"""
Ajio Spider - Scrapes fashion products from Ajio.com (Reliance Retail).

Uses Ajio's internal search API to fetch product listings with real
product URLs, INR prices, and actual product images.

Usage:
    python run_scraper.py ajio --max-products 100
    python run_scraper.py ajio --category "sneakers"
"""

import json
import logging
from typing import Iterator
from urllib.parse import quote_plus

import scrapy
from scrapy.http import Response

from fashion_scraper.items import FashionProductItem
from fashion_scraper.spiders.base import BaseFashionSpider

logger = logging.getLogger(__name__)


class AjioSpider(BaseFashionSpider):
    """
    Ajio spider using their search/listing API.

    Ajio serves product data via internal APIs that return JSON.
    No Playwright needed — direct HTTP requests work.
    """

    name = "ajio"
    source_site = "ajio"
    allowed_domains = ["ajio.com"]

    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'ROBOTSTXT_OBEY': False,
        'DEFAULT_REQUEST_HEADERS': {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-IN,en;q=0.9',
            'Referer': 'https://www.ajio.com/',
            'Origin': 'https://www.ajio.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
    }

    # Search queries mapped to our categories — multiple per category for variety
    SEARCH_QUERIES = {
        # Men's clothing
        'men t-shirts': 'Men > T-Shirts',
        'men polo t-shirts': 'Men > T-Shirts',
        'men printed t-shirts': 'Men > T-Shirts',
        'men shirts': 'Men > Shirts',
        'men casual shirts': 'Men > Shirts',
        'men formal shirts': 'Men > Shirts',
        'men jeans': 'Men > Pants',
        'men chinos': 'Men > Pants',
        'men trousers': 'Men > Pants',
        'men track pants': 'Men > Pants',
        'men jackets': 'Men > Jackets',
        'men sweatshirts': 'Men > Jackets',
        'men hoodies': 'Men > Jackets',
        'men blazers': 'Men > Jackets',
        'men shorts': 'Men > Shorts',
        # Women's clothing
        'women dresses': 'Women > Dresses',
        'women maxi dresses': 'Women > Dresses',
        'women party dresses': 'Women > Dresses',
        'women tops': 'Women > Tops',
        'women crop tops': 'Women > Tops',
        'women blouses': 'Women > Tops',
        'women t-shirts': 'Women > Tops',
        'women jeans': 'Women > Pants',
        'women trousers': 'Women > Pants',
        'women palazzos': 'Women > Pants',
        'women skirts': 'Women > Skirts',
        'women jackets': 'Women > Jackets',
        'women sweaters': 'Women > Jackets',
        # Footwear
        'sneakers': 'Accessories > Sneakers',
        'men sneakers': 'Accessories > Sneakers',
        'women sneakers': 'Accessories > Sneakers',
        'running shoes': 'Accessories > Sneakers',
        'casual shoes men': 'Accessories > Sneakers',
        'sports shoes': 'Accessories > Sneakers',
        'women heels': 'Accessories > Shoes',
        'women flats': 'Accessories > Shoes',
        'women sandals': 'Accessories > Shoes',
        'men formal shoes': 'Accessories > Shoes',
        'men loafers': 'Accessories > Shoes',
        'men sandals': 'Accessories > Shoes',
        # Accessories
        'handbags': 'Accessories > Bags',
        'backpacks': 'Accessories > Bags',
        'tote bags': 'Accessories > Bags',
        'sling bags': 'Accessories > Bags',
        'sunglasses': 'Accessories > Sunglasses',
        'men sunglasses': 'Accessories > Sunglasses',
        'watches': 'Accessories > Watches',
        'men watches': 'Accessories > Watches',
        # Ethnic Wear
        'kurta men': 'Men > Ethnic Wear',
        'kurta pajama set': 'Men > Ethnic Wear',
        'sherwani': 'Men > Ethnic Wear',
        'kurtis women': 'Women > Ethnic Wear',
        'sarees': 'Women > Ethnic Wear',
        'lehenga': 'Women > Ethnic Wear',
        'salwar suits': 'Women > Ethnic Wear',
        'anarkali': 'Women > Ethnic Wear',
    }

    # Number of pages to fetch per query (each page = ~45 products)
    PAGES_PER_QUERY = 2

    def start_requests(self):
        """Generate search API requests for each category."""
        queries = self.SEARCH_QUERIES

        # If user specified a category, filter to matching queries
        if self.category:
            cat_lower = self.category.lower()
            queries = {k: v for k, v in queries.items() if cat_lower in k.lower() or cat_lower in v.lower()}
            if not queries:
                # Use the category itself as search query
                queries = {self.category: self.category}

        for query, category in queries.items():
            for page in range(self.PAGES_PER_QUERY):
                url = f"https://www.ajio.com/api/search?query={quote_plus(query)}&curated=true&regionId=ajio&fields=SITE&gridColumns=3&currentPage={page}&pageSize=45&format=JSON&sortBy=relevance"
                yield scrapy.Request(
                    url,
                    callback=self.parse_api_response,
                    meta={'category': category, 'query': query, 'page': page},
                    dont_filter=True,
                )

    def parse_api_response(self, response: Response):
        """Parse Ajio search API JSON response."""
        category = response.meta.get('category', '')
        query = response.meta.get('query', '')

        try:
            data = json.loads(response.text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse Ajio API response for '{query}': {e}")
            # Try Playwright fallback for HTML pages
            yield scrapy.Request(
                f"https://www.ajio.com/search/?text={quote_plus(query)}",
                callback=self.parse_html_listing,
                meta={'category': category, 'playwright': True},
                dont_filter=True,
            )
            return

        # Ajio API response structure
        products = data.get('products', [])
        if not products:
            # Try alternate response structures
            products = data.get('data', {}).get('products', [])
            if not products:
                logger.warning(f"No products found for '{query}' on Ajio API, trying HTML")
                yield scrapy.Request(
                    f"https://www.ajio.com/search/?text={quote_plus(query)}",
                    callback=self.parse_html_listing,
                    meta={'category': category, 'playwright': True},
                    dont_filter=True,
                )
                return

        logger.info(f"Found {len(products)} products for '{query}' on Ajio")

        for product in products:
            if self.max_products and self.crawler.stats.get_value('item_scraped_count', 0) >= self.max_products:
                return

            item = self._parse_api_product(product, category)
            if item:
                yield item

    def _parse_api_product(self, product: dict, category: str) -> FashionProductItem:
        """Parse a single product from Ajio API response."""
        try:
            product_id = product.get('code', product.get('productId', ''))
            title = product.get('name', product.get('productName', ''))
            brand = product.get('brandName', product.get('brand', ''))

            if not product_id or not title:
                return None

            # Price
            price_data = product.get('price', {})
            if isinstance(price_data, dict):
                price = price_data.get('value', price_data.get('formattedValue', 0))
            else:
                price = price_data

            original_price_data = product.get('wasPriceData', product.get('mrp', {}))
            if isinstance(original_price_data, dict):
                original_price = original_price_data.get('value', 0)
            else:
                original_price = original_price_data

            # Handle string prices like "Rs. 1,299"
            if isinstance(price, str):
                price = float(price.replace('Rs.', '').replace(',', '').replace('₹', '').strip() or 0)
            if isinstance(original_price, str):
                original_price = float(original_price.replace('Rs.', '').replace(',', '').replace('₹', '').strip() or 0)

            # Images
            images = product.get('images', [])
            if images:
                if isinstance(images[0], dict):
                    image_url = images[0].get('url', '')
                else:
                    image_url = images[0]
            else:
                image_url = product.get('imageUrl', product.get('searchImage', ''))

            # Make image URL absolute
            if image_url and not image_url.startswith('http'):
                image_url = f"https://assets.ajio.com/medias/{image_url}"

            # Product URL
            url_key = product.get('url', product.get('fnlColorVariantData', {}).get('url', ''))
            if url_key and not url_key.startswith('http'):
                product_url = f"https://www.ajio.com{url_key}"
            elif url_key:
                product_url = url_key
            else:
                product_url = f"https://www.ajio.com/p/{product_id}"

            # Color
            color = product.get('fnlColorVariantData', {}).get('colorName', '')
            if not color:
                color = product.get('color', '')

            # Description
            description = product.get('description', '')
            if not description:
                description = f"{brand} {title}. Available on Ajio."

            return FashionProductItem(
                product_id=str(product_id),
                source_site=self.source_site,
                title=f"{brand} {title}" if brand and brand.lower() not in title.lower() else title,
                description=description,
                brand=brand,
                price=float(price) if price else None,
                original_price=float(original_price) if original_price and original_price != price else None,
                currency='INR',
                category=category,
                color=color,
                image_url=image_url,
                image_urls=[image_url] if image_url else [],
                product_url=product_url,
            )

        except Exception as e:
            logger.warning(f"Failed to parse Ajio product: {e}")
            return None

    def parse_html_listing(self, response: Response):
        """Fallback: parse HTML listing page (when API doesn't work)."""
        category = response.meta.get('category', '')

        # Try to extract __NEXT_DATA__ JSON (Next.js pattern)
        script_data = response.css('script#__NEXT_DATA__::text').get()
        if script_data:
            try:
                data = json.loads(script_data)
                products = (data.get('props', {}).get('pageProps', {})
                           .get('grid', {}).get('products', []))
                for product in products:
                    if self.max_products and self.crawler.stats.get_value('item_scraped_count', 0) >= self.max_products:
                        return
                    item = self._parse_api_product(product, category)
                    if item:
                        yield item
                return
            except json.JSONDecodeError:
                pass

        # Fallback: parse product cards from HTML
        cards = response.css('div[class*="product"]')
        logger.info(f"Found {len(cards)} product cards on Ajio HTML page")

        for card in cards:
            if self.max_products and self.crawler.stats.get_value('item_scraped_count', 0) >= self.max_products:
                return

            title = card.css('div[class*="nameCls"] ::text').get()
            brand = card.css('div[class*="brand"] ::text').get()
            price = card.css('span[class*="price"] ::text').get()
            image = card.css('img::attr(src)').get() or card.css('img::attr(data-src)').get()
            link = card.css('a::attr(href)').get()

            if not title or not link:
                continue

            product_url = response.urljoin(link)
            product_id = link.split('/')[-1] if link else ''

            # Clean price
            price_val = None
            if price:
                price_clean = price.replace('Rs.', '').replace(',', '').replace('₹', '').strip()
                try:
                    price_val = float(price_clean)
                except ValueError:
                    pass

            if image and not image.startswith('http'):
                image = f"https:{image}" if image.startswith('//') else response.urljoin(image)

            yield FashionProductItem(
                product_id=str(product_id),
                source_site=self.source_site,
                title=f"{brand} {title}" if brand else title,
                brand=brand or '',
                price=price_val,
                currency='INR',
                category=category,
                image_url=image or '',
                image_urls=[image] if image else [],
                product_url=product_url,
            )

    def parse_product(self, response: Response) -> Iterator[FashionProductItem]:
        """Parse individual product page (not typically used)."""
        pass
