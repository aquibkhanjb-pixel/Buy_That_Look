"""
Validation Pipeline - Validates required fields in scraped items.
"""

import logging
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class ValidationPipeline:
    """
    Validates that items have all required fields.

    Drops items missing critical fields like title, image_url, or product_url.
    """

    REQUIRED_FIELDS = ['title', 'image_url', 'product_url', 'product_id', 'source_site']

    def process_item(self, item, spider):
        """Validate item has required fields."""
        missing_fields = []

        for field in self.REQUIRED_FIELDS:
            value = item.get(field)
            if not value or (isinstance(value, str) and not value.strip()):
                missing_fields.append(field)

        if missing_fields:
            raise DropItem(f"Missing required fields: {missing_fields}")

        # Validate URL formats
        if not item['product_url'].startswith('http'):
            raise DropItem(f"Invalid product URL: {item['product_url']}")

        if not item['image_url'].startswith('http'):
            raise DropItem(f"Invalid image URL: {item['image_url']}")

        # Validate price if present
        if item.get('price') is not None:
            try:
                price = float(item['price'])
                if price < 0:
                    raise DropItem(f"Invalid price: {price}")
            except (ValueError, TypeError):
                raise DropItem(f"Invalid price format: {item['price']}")

        logger.debug(f"Validated: {item['title'][:50]}...")
        return item
