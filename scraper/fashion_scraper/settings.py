"""
Scrapy settings for Fashion Scraper project.

For simplicity, this file contains only settings considered important or
commonly used. See documentation for more settings:
https://docs.scrapy.org/en/latest/topics/settings.html
"""

import os
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR.parent / "data"
IMAGES_DIR = DATA_DIR / "images"

# Ensure directories exist
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Bot name
BOT_NAME = "fashion_scraper"

# Spider modules
SPIDER_MODULES = ["fashion_scraper.spiders"]
NEWSPIDER_MODULE = "fashion_scraper.spiders"

# Crawl responsibly by identifying yourself
USER_AGENT = "FashionRecommendationBot/1.0 (+https://github.com/yourusername/fashion-recommendation)"

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests
CONCURRENT_REQUESTS = 8

# Configure a delay for requests (be polite to servers)
DOWNLOAD_DELAY = 2
RANDOMIZE_DOWNLOAD_DELAY = True

# Disable cookies (enabled by default)
COOKIES_ENABLED = True

# Disable Telnet Console (enabled by default)
TELNETCONSOLE_ENABLED = False

# Override the default request headers
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

# Enable or disable spider middlewares
SPIDER_MIDDLEWARES = {
    "fashion_scraper.middlewares.FashionScraperSpiderMiddleware": 543,
}

# Enable or disable downloader middlewares
DOWNLOADER_MIDDLEWARES = {
    "fashion_scraper.middlewares.FashionScraperDownloaderMiddleware": 543,
    "fashion_scraper.middlewares.RandomUserAgentMiddleware": 400,
    "fashion_scraper.middlewares.RetryMiddleware": 550,
}

# Enable or disable extensions
EXTENSIONS = {
    "scrapy.extensions.telnet.TelnetConsole": None,
    "scrapy.extensions.throttle.AutoThrottle": 500,
}

# Configure item pipelines
ITEM_PIPELINES = {
    "fashion_scraper.pipelines.ValidationPipeline": 100,
    "fashion_scraper.pipelines.CleaningPipeline": 200,
    "fashion_scraper.pipelines.DuplicatesPipeline": 300,
    # "fashion_scraper.pipelines.ImagePipeline": 400,  # Enable when image download is needed
    "fashion_scraper.pipelines.DatabasePipeline": 500,
}

# Enable and configure the AutoThrottle extension
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 86400  # 24 hours
HTTPCACHE_DIR = str(BASE_DIR / ".scrapy" / "httpcache")
HTTPCACHE_IGNORE_HTTP_CODES = [500, 502, 503, 504, 408, 429]
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Retry settings
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# Image pipeline settings
IMAGES_STORE = str(IMAGES_DIR)
IMAGES_URLS_FIELD = "image_urls"
IMAGES_RESULT_FIELD = "images"
IMAGES_MIN_HEIGHT = 100
IMAGES_MIN_WIDTH = 100

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_FILE = str(BASE_DIR / "logs" / "scraper.log")

# Ensure log directory exists
(BASE_DIR / "logs").mkdir(exist_ok=True)

# Database settings (from environment)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://fashionuser:fashionpass@localhost:5432/fashiondb"
)

# Request fingerprinter
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

# Twisted reactor (required for Playwright spiders)
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# Playwright settings (for JS-rendered sites: Myntra, Ajio, Flipkart, Amazon)
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}

# Feed exports
FEEDS = {
    str(DATA_DIR / "products_%(time)s.json"): {
        "format": "json",
        "encoding": "utf8",
        "indent": 2,
    },
}

# Close spider settings
CLOSESPIDER_ITEMCOUNT = 0  # 0 = no limit
CLOSESPIDER_PAGECOUNT = 0
CLOSESPIDER_ERRORCOUNT = 50
