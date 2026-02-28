"""
Cleaning Pipeline - Cleans and normalizes scraped data.
"""

import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Category mapping to standardize across sites
CATEGORY_MAPPING = {
    # Women's clothing
    'dresses': 'Women > Dresses',
    'dress': 'Women > Dresses',
    'women dresses': 'Women > Dresses',
    'tops': 'Women > Tops',
    'women tops': 'Women > Tops',
    'blouses': 'Women > Tops',
    'shirts': 'Women > Tops',
    'women shirts': 'Women > Tops',
    'pants': 'Women > Pants',
    'women pants': 'Women > Pants',
    'trousers': 'Women > Pants',
    'jeans': 'Women > Pants',
    'women jeans': 'Women > Pants',
    'skirts': 'Women > Skirts',
    'women skirts': 'Women > Skirts',

    # Men's clothing
    'men shirts': 'Men > Shirts',
    'men tops': 'Men > Shirts',
    'men tshirts': 'Men > T-Shirts',
    'men t-shirts': 'Men > T-Shirts',
    'tshirts': 'Men > T-Shirts',
    't-shirts': 'Men > T-Shirts',
    'men pants': 'Men > Pants',
    'men jeans': 'Men > Pants',
    'men trousers': 'Men > Pants',
    'jackets': 'Men > Jackets',
    'men jackets': 'Men > Jackets',
    'blazers': 'Men > Jackets',

    # Accessories
    'bags': 'Accessories > Bags',
    'handbags': 'Accessories > Bags',
    'purses': 'Accessories > Bags',
    'backpacks': 'Accessories > Bags',
    'shoes': 'Accessories > Shoes',
    'sneakers': 'Accessories > Sneakers',
    'casual shoes': 'Accessories > Sneakers',
    'sports shoes': 'Accessories > Sneakers',
    'running shoes': 'Accessories > Sneakers',
    'heels': 'Accessories > Shoes',
    'sandals': 'Accessories > Shoes',
    'boots': 'Accessories > Shoes',
    'loafers': 'Accessories > Shoes',
    'flip flops': 'Accessories > Shoes',
    'flats': 'Accessories > Shoes',
    'jewelry': 'Accessories > Jewelry',
    'jewellery': 'Accessories > Jewelry',
    'watches': 'Accessories > Watches',
    'sunglasses': 'Accessories > Sunglasses',
    'hats': 'Accessories > Hats',
    'caps': 'Accessories > Hats',

    # Indian fashion
    'kurtas': 'Men > Ethnic Wear',
    'kurta': 'Men > Ethnic Wear',
    'kurtis': 'Women > Ethnic Wear',
    'kurti': 'Women > Ethnic Wear',
    'sarees': 'Women > Ethnic Wear',
    'saree': 'Women > Ethnic Wear',
    'lehengas': 'Women > Ethnic Wear',
    'lehenga': 'Women > Ethnic Wear',
    'salwar': 'Women > Ethnic Wear',
    'churidar': 'Women > Ethnic Wear',
    'sherwani': 'Men > Ethnic Wear',
    'dupatta': 'Women > Ethnic Wear',
}

# Currency mapping
CURRENCY_SYMBOLS = {
    '$': 'USD',
    '₹': 'INR',
    '€': 'EUR',
    '£': 'GBP',
    '¥': 'JPY',
}


class CleaningPipeline:
    """
    Cleans and normalizes product data.

    - Strips whitespace
    - Standardizes categories
    - Normalizes prices and currencies
    - Extracts brand from title if missing
    """

    def process_item(self, item, spider):
        """Clean and normalize item fields."""

        # Clean title
        if item.get('title'):
            item['title'] = self._clean_text(item['title'])

        # Clean description
        if item.get('description'):
            item['description'] = self._clean_text(item['description'])

        # Standardize category
        if item.get('category'):
            item['category'] = self._standardize_category(item['category'])

        # Extract subcategory
        if item.get('category') and ' > ' in item['category']:
            parts = item['category'].split(' > ')
            item['subcategory'] = parts[-1] if len(parts) > 1 else None

        # Normalize currency
        item['currency'] = self._extract_currency(item)

        # Clean brand
        if item.get('brand'):
            item['brand'] = self._clean_text(item['brand'])

        # Clean color
        if item.get('color'):
            item['color'] = self._clean_text(item['color']).capitalize()

        # Add timestamp
        item['scraped_at'] = datetime.utcnow().isoformat()

        # Ensure image_urls list exists for ImagePipeline
        if item.get('image_url') and not item.get('image_urls'):
            item['image_urls'] = [item['image_url']]
            if item.get('additional_images'):
                item['image_urls'].extend(item['additional_images'])

        logger.debug(f"Cleaned: {item['title'][:50]}...")
        return item

    def _clean_text(self, text: str) -> str:
        """Remove extra whitespace and clean text."""
        if not text:
            return text
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters at start/end
        text = text.strip(' \t\n\r\'"')
        return text

    def _standardize_category(self, category: str) -> str:
        """Map category to standardized taxonomy."""
        if not category:
            return category

        # If already in our taxonomy format (e.g., "Men > Pants"), keep it
        if ' > ' in category:
            return category

        category_lower = category.lower().strip()

        # Check direct mapping
        if category_lower in CATEGORY_MAPPING:
            return CATEGORY_MAPPING[category_lower]

        # Check partial matches
        for key, value in CATEGORY_MAPPING.items():
            if key in category_lower:
                return value

        # Return original if no mapping found
        return category

    def _extract_currency(self, item) -> str:
        """Extract currency from price string or default."""
        # If currency already set
        if item.get('currency'):
            return item['currency'].upper()

        # Try to extract from price field (if it was stored as string)
        price_str = str(item.get('price', ''))
        for symbol, code in CURRENCY_SYMBOLS.items():
            if symbol in price_str:
                return code

        # Default based on source site
        source = item.get('source_site', '').lower()
        if source in ['myntra', 'flipkart', 'ajio', 'amazon_india']:
            return 'INR'
        elif source in ['asos']:
            return 'GBP'

        return 'USD'  # Default
