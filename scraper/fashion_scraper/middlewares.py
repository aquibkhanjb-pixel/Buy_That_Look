"""
Scrapy Middlewares for Fashion Scraper.

Includes:
- Spider middleware for processing spider input/output
- Downloader middleware for request/response processing
- User-agent rotation
- Retry logic
"""

import random
import logging
from typing import Optional

from scrapy import signals
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.exceptions import IgnoreRequest

logger = logging.getLogger(__name__)


# Common user agents for rotation
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


class FashionScraperSpiderMiddleware:
    """
    Spider middleware for processing spider input/output.
    """

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response: Response, spider: Spider):
        """Process response before it reaches the spider."""
        return None

    def process_spider_output(self, response: Response, result, spider: Spider):
        """Process items/requests yielded from spider."""
        for item_or_request in result:
            yield item_or_request

    def process_spider_exception(self, response: Response, exception: Exception, spider: Spider):
        """Handle exceptions raised by spider."""
        logger.error(f"Spider exception: {exception} for {response.url}")
        return None

    def process_start_requests(self, start_requests, spider: Spider):
        """Process start requests."""
        for request in start_requests:
            yield request

    def spider_opened(self, spider: Spider):
        """Called when spider opens."""
        logger.info(f"Spider opened: {spider.name}")


class FashionScraperDownloaderMiddleware:
    """
    Downloader middleware for request/response processing.
    """

    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request: Request, spider: Spider) -> Optional[Request]:
        """Process request before downloading."""
        # Log request
        logger.debug(f"Requesting: {request.url}")
        return None

    def process_response(self, request: Request, response: Response, spider: Spider) -> Response:
        """Process response after downloading."""
        # Check for blocked responses
        if response.status in [403, 429]:
            logger.warning(f"Blocked ({response.status}): {request.url}")

        return response

    def process_exception(self, request: Request, exception: Exception, spider: Spider):
        """Handle download exceptions."""
        logger.error(f"Download exception: {exception} for {request.url}")
        return None

    def spider_opened(self, spider: Spider):
        """Called when spider opens."""
        logger.info(f"Downloader middleware enabled for: {spider.name}")


class RandomUserAgentMiddleware:
    """
    Middleware to rotate user agents randomly.

    Helps avoid detection by varying the browser fingerprint.
    """

    def __init__(self, user_agents: list = None):
        self.user_agents = user_agents or USER_AGENTS

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request: Request, spider: Spider) -> None:
        """Set random user agent for each request."""
        user_agent = random.choice(self.user_agents)
        request.headers['User-Agent'] = user_agent


class RetryMiddleware:
    """
    Enhanced retry middleware with exponential backoff.
    """

    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        return cls(
            max_retries=settings.getint('RETRY_TIMES', 3),
        )

    def process_response(self, request: Request, response: Response, spider: Spider) -> Response:
        """Retry on certain response codes."""
        retry_codes = [500, 502, 503, 504, 408, 429]

        if response.status in retry_codes:
            retries = request.meta.get('retry_times', 0)

            if retries < self.max_retries:
                logger.info(f"Retrying ({retries + 1}/{self.max_retries}): {request.url}")

                new_request = request.copy()
                new_request.meta['retry_times'] = retries + 1
                new_request.dont_filter = True

                # Exponential backoff would be handled by AutoThrottle
                return new_request
            else:
                logger.warning(f"Max retries reached for: {request.url}")

        return response

    def process_exception(self, request: Request, exception: Exception, spider: Spider):
        """Retry on connection errors."""
        retries = request.meta.get('retry_times', 0)

        if retries < self.max_retries:
            logger.info(f"Retrying after exception ({retries + 1}/{self.max_retries}): {request.url}")

            new_request = request.copy()
            new_request.meta['retry_times'] = retries + 1
            new_request.dont_filter = True

            return new_request

        return None
