"""
Duplicates Pipeline - Filters duplicate products.
"""

import logging
import hashlib
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class DuplicatesPipeline:
    """
    Filters duplicate products based on product_id and source_site.

    Uses in-memory set for current crawl and can check database
    for historical duplicates.
    """

    def __init__(self):
        self.seen_ids = set()
        self.seen_titles = set()

    def process_item(self, item, spider):
        """Check for duplicates and drop if found."""

        # Create unique identifier
        unique_id = f"{item['source_site']}:{item['product_id']}"

        if unique_id in self.seen_ids:
            raise DropItem(f"Duplicate product ID: {unique_id}")

        # Also check title similarity (fuzzy duplicate detection)
        title_hash = self._hash_title(item['title'])
        if title_hash in self.seen_titles:
            logger.warning(f"Possible duplicate title: {item['title'][:50]}...")
            # Don't drop, just warn (titles can be similar for different products)

        # Add to seen sets
        self.seen_ids.add(unique_id)
        self.seen_titles.add(title_hash)

        return item

    def _hash_title(self, title: str) -> str:
        """Create hash of normalized title for comparison."""
        if not title:
            return ""

        # Normalize: lowercase, remove special chars, sort words
        normalized = title.lower()
        normalized = ''.join(c for c in normalized if c.isalnum() or c.isspace())
        words = sorted(normalized.split())
        normalized = ' '.join(words)

        # Create hash
        return hashlib.md5(normalized.encode()).hexdigest()

    def open_spider(self, spider):
        """Called when spider opens."""
        self.seen_ids.clear()
        self.seen_titles.clear()
        logger.info("Duplicates pipeline initialized")

    def close_spider(self, spider):
        """Called when spider closes."""
        logger.info(f"Processed {len(self.seen_ids)} unique products")
