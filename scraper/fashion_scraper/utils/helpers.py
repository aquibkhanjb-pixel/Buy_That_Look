"""
Helper utilities for fashion scraper.
"""

import re
import hashlib
from urllib.parse import urlparse, urljoin, parse_qs, urlencode
from typing import Optional


def clean_price(price_str: str) -> Optional[float]:
    """
    Extract numeric price from a price string.

    Examples:
        "$49.99" -> 49.99
        "Rs. 1,999" -> 1999.0
        "€29.00 EUR" -> 29.0

    Args:
        price_str: Raw price string

    Returns:
        Float price or None if parsing fails
    """
    if not price_str:
        return None

    # Remove currency symbols and non-numeric chars except decimal point
    cleaned = re.sub(r'[^\d.]', '', str(price_str))

    # Handle multiple decimal points (e.g., "1.999.00")
    parts = cleaned.split('.')
    if len(parts) > 2:
        # Keep last part as decimal
        cleaned = ''.join(parts[:-1]) + '.' + parts[-1]

    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def extract_color(text: str) -> Optional[str]:
    """
    Extract color name from product text.

    Args:
        text: Product title or description

    Returns:
        Extracted color or None
    """
    if not text:
        return None

    # Common color names
    colors = {
        'red', 'blue', 'green', 'yellow', 'orange', 'purple', 'pink',
        'black', 'white', 'gray', 'grey', 'brown', 'navy', 'beige',
        'burgundy', 'teal', 'coral', 'maroon', 'olive', 'cream',
        'gold', 'silver', 'rose', 'mint', 'lavender', 'turquoise',
        'charcoal', 'ivory', 'khaki', 'tan', 'peach', 'magenta',
        'cyan', 'indigo', 'violet', 'crimson', 'scarlet', 'azure',
    }

    # Color modifiers
    modifiers = {'light', 'dark', 'bright', 'pale', 'deep', 'royal', 'baby', 'hot', 'dusty'}

    text_lower = text.lower()
    words = text_lower.split()

    # Check for modifier + color combinations
    for i, word in enumerate(words):
        if word in colors:
            # Check for modifier before color
            if i > 0 and words[i-1] in modifiers:
                return f"{words[i-1].capitalize()} {word.capitalize()}"
            return word.capitalize()

    return None


def generate_product_id(url: str, title: str = None) -> str:
    """
    Generate a unique product ID from URL and title.

    Args:
        url: Product URL
        title: Product title (optional)

    Returns:
        Unique product ID string
    """
    # Try to extract ID from URL first
    patterns = [
        r'/product/([A-Za-z0-9_-]+)',
        r'/p/([A-Za-z0-9_-]+)',
        r'/dp/([A-Za-z0-9]+)',
        r'/item/([A-Za-z0-9_-]+)',
        r'[?&]id=([A-Za-z0-9_-]+)',
        r'[?&]pid=([A-Za-z0-9_-]+)',
        r'[?&]sku=([A-Za-z0-9_-]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    # Fallback: generate hash from URL + title
    hash_input = url
    if title:
        hash_input += title

    return hashlib.md5(hash_input.encode()).hexdigest()[:16]


def normalize_url(url: str, base_url: str = None) -> str:
    """
    Normalize a URL by making it absolute and removing tracking params.

    Args:
        url: URL to normalize
        base_url: Base URL for resolving relative URLs

    Returns:
        Normalized absolute URL
    """
    if not url:
        return url

    # Make absolute
    if url.startswith('//'):
        url = 'https:' + url
    elif url.startswith('/') and base_url:
        url = urljoin(base_url, url)

    # Parse URL
    parsed = urlparse(url)

    # Remove common tracking parameters
    tracking_params = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'ref', 'ref_', 'gclid', 'fbclid', 'mc_cid', 'mc_eid',
        'source', 'campaign', 'click_id', 'affiliate',
    }

    if parsed.query:
        params = parse_qs(parsed.query)
        # Filter out tracking params
        filtered = {k: v[0] for k, v in params.items() if k.lower() not in tracking_params}
        # Rebuild URL
        if filtered:
            new_query = urlencode(filtered)
            url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"
        else:
            url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    return url


def extract_brand_from_title(title: str) -> Optional[str]:
    """
    Try to extract brand name from product title.

    Many products have brand as the first word(s) in the title.

    Args:
        title: Product title

    Returns:
        Extracted brand or None
    """
    if not title:
        return None

    # Common brand name patterns
    # Brand is often first word before specific keywords
    title_parts = title.split()

    if len(title_parts) >= 2:
        # Check if first word is likely a brand (capitalized, not a common word)
        first_word = title_parts[0]
        common_words = {'the', 'a', 'an', 'new', 'best', 'top', 'premium', 'quality'}

        if first_word.lower() not in common_words and first_word[0].isupper():
            # Could be a brand - return first 1-2 words
            if len(title_parts) > 2 and title_parts[1][0].isupper():
                return f"{title_parts[0]} {title_parts[1]}"
            return title_parts[0]

    return None
