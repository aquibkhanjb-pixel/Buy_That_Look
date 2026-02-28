"""
Logging configuration using loguru.
Provides structured logging with context.
"""

import sys
from loguru import logger

from app.config import get_settings


def setup_logging():
    """Configure application logging."""
    settings = get_settings()

    # Remove default handler
    logger.remove()

    # Console logging
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        format=log_format,
        level="DEBUG" if settings.debug else "INFO",
        colorize=True,
    )

    # File logging (production)
    if not settings.debug:
        logger.add(
            "logs/app_{time:YYYY-MM-DD}.log",
            rotation="1 day",
            retention="30 days",
            compression="gz",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level="INFO",
        )

    return logger
