"""
Item Pipelines for Fashion Scraper.

Processing pipeline:
1. ValidationPipeline - Validate required fields
2. CleaningPipeline - Clean and normalize data
3. DuplicatesPipeline - Filter duplicate products
4. ImagePipeline - Download and process images
5. DatabasePipeline - Store in PostgreSQL
"""

from .validation import ValidationPipeline
from .cleaning import CleaningPipeline
from .duplicates import DuplicatesPipeline
from .images import ImagePipeline
from .database import DatabasePipeline

__all__ = [
    "ValidationPipeline",
    "CleaningPipeline",
    "DuplicatesPipeline",
    "ImagePipeline",
    "DatabasePipeline",
]
