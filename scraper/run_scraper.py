"""
Run scraper from command line.

Usage:
    python run_scraper.py demo --max-products 50
    python run_scraper.py generic --url https://example.com/products
    python run_scraper.py generic --config configs/mysite.json
"""

import argparse
import sys
import os
from pathlib import Path

# Add scraper to path
sys.path.insert(0, str(Path(__file__).parent))

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


def run_spider(spider_name: str, **kwargs):
    """Run a spider with the given arguments."""
    # Get Scrapy settings
    os.chdir(Path(__file__).parent)
    settings = get_project_settings()

    # Create crawler process
    process = CrawlerProcess(settings)

    # Add spider with arguments
    process.crawl(spider_name, **kwargs)

    # Start crawling
    print(f"\n{'='*60}")
    print(f"Starting {spider_name} spider")
    print(f"{'='*60}\n")

    process.start()

    print(f"\n{'='*60}")
    print("Crawling complete!")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Fashion Product Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run demo spider (uses Fake Store API)
  python run_scraper.py demo --max-products 20

  # Run generic spider with URL
  python run_scraper.py generic --url https://example.com/products

  # Run generic spider with config file
  python run_scraper.py generic --config configs/mysite.json

  # Run with category filter
  python run_scraper.py demo --category "women's clothing"
        """
    )

    parser.add_argument(
        'spider',
        choices=['demo', 'generic', 'myntra', 'ajio', 'flipkart', 'amazon_india'],
        help='Spider to run'
    )
    parser.add_argument(
        '--max-products', '-n',
        type=int,
        default=0,
        help='Maximum number of products to scrape (0 = no limit)'
    )
    parser.add_argument(
        '--category', '-c',
        help='Filter by category'
    )
    parser.add_argument(
        '--url', '-u',
        help='Start URL (for generic spider)'
    )
    parser.add_argument(
        '--config',
        help='Path to config JSON file (for generic spider)'
    )
    parser.add_argument(
        '--source-site', '-s',
        help='Source site name'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output file path'
    )

    args = parser.parse_args()

    # Build spider arguments
    spider_kwargs = {}

    if args.max_products:
        spider_kwargs['max_products'] = args.max_products
    if args.category:
        spider_kwargs['category'] = args.category
    if args.url:
        spider_kwargs['url'] = args.url
    if args.config:
        spider_kwargs['config'] = args.config
    if args.source_site:
        spider_kwargs['source_site'] = args.source_site

    # Run spider
    run_spider(args.spider, **spider_kwargs)


if __name__ == '__main__':
    main()
