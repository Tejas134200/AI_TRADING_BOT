"""
module1_news_collector/nse_bse_scraper.py
------------------------------------------
Scrapes corporate announcements directly from NSE India.

This is the most valuable source — company filings appear here
BEFORE media picks them up. Covers:
  - Board meeting outcomes (dividend, buyback)
  - Quarterly results
  - Mergers & acquisitions
  - Regulatory filings

URL: https://www.nseindia.com/companies-listing/corporate-filings-announcements

Note: NSE has bot detection. We use realistic headers + session
cookies. If blocked, switch to the NSE data API (requires registration).
"""

import logging
import time
from datetime import datetime
from typing import List

import requests
from bs4 import BeautifulSoup

from module1_news_collector.normalizer import Article

logger = logging.getLogger(__name__)

NSE_ANNOUNCEMENTS_URL = (
    "https://www.nseindia.com/api/corp-info?"
    "index=equities&type=announcement&desc=announcements"
)

# Realistic browser headers to avoid bot detection
HEADERS = {
    "User-Agent"      : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept"          : "application/json, text/plain, */*",
    "Accept-Language" : "en-IN,en;q=0.9",
    "Referer"         : "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}


def fetch() -> List[Article]:
    """
    Fetch latest NSE corporate announcements.
    Returns list of Article objects.
    """
    articles = []
    session = requests.Session()

    try:
        # Step 1: Hit the main page first to get session cookies (NSE requires this)
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
        time.sleep(1)   # polite delay

        # Step 2: Hit the announcements API
        response = session.get(NSE_ANNOUNCEMENTS_URL, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        for item in data.get("data", [])[:30]:  # latest 30 announcements
            try:
                title = item.get("desc", "") or item.get("subject", "")
                ticker = item.get("symbol", "")
                body = item.get("attchmntText", "") or title

                article = Article(
                    title        = f"{ticker}: {title}",
                    content      = body,
                    source       = "nse_bse",
                    url          = f"https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                    published_at = _parse_date(item.get("exchdisstime") or item.get("an_dt")),
                    ticker_hint  = ticker,
                )
                if article.title:
                    articles.append(article)

            except Exception as e:
                logger.warning(f"[nse_bse] Skipping announcement: {e}")

    except requests.RequestException as e:
        logger.error(f"[nse_bse] Failed to fetch announcements: {e}")
    except Exception as e:
        logger.error(f"[nse_bse] Unexpected error: {e}")

    logger.info(f"[nse_bse] Fetched {len(articles)} announcements")
    return articles


def _parse_date(date_str: str) -> datetime:
    if not date_str:
        return datetime.utcnow()
    # NSE uses formats like "09-Apr-2026 10:30:00" or "2026-04-09T10:30:00"
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str[:19], fmt)
        except ValueError:
            continue
    return datetime.utcnow()