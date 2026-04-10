"""
module1_news_collector/google_news_fetcher.py
----------------------------------------------
Fetches from Google News RSS feeds — no API key required.

Google News RSS gives real-time headlines. We search for
Indian market-specific topics and parse the XML feed.

Library: feedparser (pip install feedparser)
"""

import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List
from urllib.parse import quote

import feedparser

from module1_news_collector.normalizer import Article

logger = logging.getLogger(__name__)

# Google News RSS endpoint
GN_RSS_BASE = "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

SEARCH_TOPICS = [
    "NSE BSE stock results India",
    "Nifty Sensex earnings today",
    "India stock acquisition merger",
    "RBI policy India market",
    "Indian company quarterly results",
]


def fetch() -> List[Article]:
    """
    Parse Google News RSS feeds for each search topic.
    Returns a list of normalized Article objects.
    """
    articles = []

    for topic in SEARCH_TOPICS:
        url = GN_RSS_BASE.format(query=quote(topic))
        try:
            feed = feedparser.parse(url)

            for entry in feed.entries:
                try:
                    article = Article(
                        title        = entry.get("title", ""),
                        content      = entry.get("summary", ""),
                        source       = "google_news",
                        url          = entry.get("link", ""),
                        published_at = _parse_date(entry),
                        ticker_hint  = _extract_ticker_hint(entry.get("title", "")),
                    )
                    if article.title:
                        articles.append(article)
                except Exception as e:
                    logger.warning(f"[google_news] Skipping entry: {e}")

        except Exception as e:
            logger.error(f"[google_news] Feed parse failed for '{topic}': {e}")

    logger.info(f"[google_news] Fetched {len(articles)} articles")
    return articles


def _parse_date(entry) -> datetime:
    """Extract published date from RSS entry."""
    try:
        if entry.get("published"):
            return parsedate_to_datetime(entry.published).replace(tzinfo=None)
    except Exception:
        pass
    return datetime.utcnow()


def _extract_ticker_hint(title: str) -> str:
    import re
    tickers = re.findall(r'\b[A-Z]{2,5}\b', title)
    return tickers[0] if tickers else ""