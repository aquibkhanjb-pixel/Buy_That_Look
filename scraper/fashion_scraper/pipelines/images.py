"""
Image Pipeline - Downloads and processes product images.
"""

import logging
import hashlib
from pathlib import Path
from urllib.parse import urlparse

from scrapy.pipelines.images import ImagesPipeline
from scrapy.http import Request
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class ImagePipeline(ImagesPipeline):
    """
    Custom image pipeline for fashion products.

    Features:
    - Downloads product images
    - Validates image dimensions
    - Creates organized directory structure
    - Generates image hashes for deduplication
    """

    def get_media_requests(self, item, info):
        """Generate requests for image downloads."""
        image_urls = item.get('image_urls', [])

        if not image_urls and item.get('image_url'):
            image_urls = [item['image_url']]

        for url in image_urls:
            if url:
                yield Request(
                    url,
                    meta={
                        'product_id': item.get('product_id'),
                        'source_site': item.get('source_site'),
                    }
                )

    def file_path(self, request, response=None, info=None, *, item=None):
        """
        Generate file path for downloaded image.

        Structure: {source_site}/{product_id}/{image_hash}.jpg
        """
        # Extract metadata
        product_id = request.meta.get('product_id', 'unknown')
        source_site = request.meta.get('source_site', 'unknown')

        # Generate image hash from URL
        url_hash = hashlib.md5(request.url.encode()).hexdigest()[:12]

        # Get extension from URL
        parsed = urlparse(request.url)
        ext = Path(parsed.path).suffix.lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            ext = '.jpg'

        # Create path
        return f"{source_site}/{product_id}/{url_hash}{ext}"

    def item_completed(self, results, item, info):
        """
        Called when all images for an item have been downloaded.

        Updates item with local image paths.
        """
        downloaded_images = []

        for success, result in results:
            if success:
                downloaded_images.append({
                    'url': result['url'],
                    'path': result['path'],
                    'checksum': result.get('checksum'),
                })
            else:
                logger.warning(f"Failed to download image: {result}")

        if not downloaded_images:
            # Don't drop item, just log warning
            logger.warning(f"No images downloaded for: {item.get('title', 'Unknown')[:50]}")
        else:
            # Update item with downloaded image info
            item['images'] = downloaded_images
            # Update image_url to local path
            item['local_image_path'] = downloaded_images[0]['path']

            logger.debug(f"Downloaded {len(downloaded_images)} images for: {item['product_id']}")

        return item

    def get_images(self, response, request, info, *, item=None):
        """Process downloaded images."""
        for key, image, buf in super().get_images(response, request, info, item=item):
            # Could add additional processing here:
            # - Resize images
            # - Convert to standard format
            # - Generate thumbnails
            yield key, image, buf
