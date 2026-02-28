"""
Fashion product spiders for various e-commerce sites.

Available spiders:
- demo: Demo spider using fake store API for testing
- generic: Generic spider that can be configured for any site
"""

from .base import BaseFashionSpider
from .demo import DemoSpider
from .generic import GenericFashionSpider

__all__ = [
    "BaseFashionSpider",
    "DemoSpider",
    "GenericFashionSpider",
]
