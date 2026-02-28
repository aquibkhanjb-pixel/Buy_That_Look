"""
Scrapy Items for Fashion Products.

Defines the data structure for scraped fashion products.
"""

import scrapy
from scrapy.loader import ItemLoader
from itemloaders.processors import TakeFirst, MapCompose, Join, Identity
from w3lib.html import remove_tags
import re


def clean_text(text):
    """Clean text by removing extra whitespace and HTML tags."""
    if text is None:
        return None
    text = remove_tags(str(text))
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def clean_price(price_str):
    """Extract numeric price from string."""
    if price_str is None:
        return None
    # Remove currency symbols and commas
    price_str = re.sub(r'[^\d.]', '', str(price_str))
    try:
        return float(price_str) if price_str else None
    except ValueError:
        return None


def extract_color(text):
    """Extract color from product title or description."""
    if text is None:
        return None

    colors = [
        'red', 'blue', 'green', 'yellow', 'orange', 'purple', 'pink',
        'black', 'white', 'gray', 'grey', 'brown', 'navy', 'beige',
        'burgundy', 'teal', 'coral', 'maroon', 'olive', 'cream',
        'gold', 'silver', 'rose', 'mint', 'lavender', 'turquoise',
    ]

    text_lower = text.lower()
    for color in colors:
        if color in text_lower:
            return color.capitalize()
    return None


class FashionProductItem(scrapy.Item):
    """
    Fashion product item with all relevant metadata.

    Fields match the Product model in the backend.
    """

    # Identifiers
    product_id = scrapy.Field()  # Source site's product ID
    source_site = scrapy.Field()  # e.g., 'amazon', 'myntra'

    # Product details
    title = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst()
    )
    description = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=Join(' ')
    )
    brand = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst()
    )

    # Pricing
    price = scrapy.Field(
        input_processor=MapCompose(clean_price),
        output_processor=TakeFirst()
    )
    original_price = scrapy.Field(
        input_processor=MapCompose(clean_price),
        output_processor=TakeFirst()
    )
    currency = scrapy.Field(
        output_processor=TakeFirst()
    )

    # Categorization
    category = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst()
    )
    subcategory = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst()
    )
    color = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst()
    )
    size = scrapy.Field(
        output_processor=TakeFirst()
    )

    # Images
    image_url = scrapy.Field(
        output_processor=TakeFirst()
    )
    image_urls = scrapy.Field(
        output_processor=Identity()
    )
    additional_images = scrapy.Field(
        output_processor=Identity()
    )
    images = scrapy.Field()  # Populated by ImagePipeline

    # URLs
    product_url = scrapy.Field(
        output_processor=TakeFirst()
    )

    # Metadata
    scraped_at = scrapy.Field()
    raw_data = scrapy.Field()  # Store raw response for debugging


class FashionProductLoader(ItemLoader):
    """
    Item loader with default processors for fashion products.
    """
    default_item_class = FashionProductItem
    default_output_processor = TakeFirst()

    def load_item(self):
        """Load item and extract color from title if not set."""
        item = super().load_item()

        # Auto-extract color from title if not set
        if not item.get('color') and item.get('title'):
            item['color'] = extract_color(item['title'])

        return item
