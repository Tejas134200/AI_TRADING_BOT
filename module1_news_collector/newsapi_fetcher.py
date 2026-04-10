"""
module1_news_collector/newsapi_fetcher.py
------------------------------------------
Fetches financial news from NewsAPI.org.

Docs: https://newsapi.org/docs/endpoints/everything
Free tier: 100 requests/day, articles up to 1 month old.
Paid tier: real-time, full content.

Returns a list of Article objects.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import requests

from config.settings import NEWSAPI_KEY
from module1_news_collector.normalizer import Article

logger = logging.getLogger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/everything"

# Indian market focused queries — adjust as needed
SEARCH_QUERIES = [
    "NSE stock earnings",
    "BSE India acquisition merger",
    "India stock market rally",
    "Sensex Nifty results",
    "Indian company profit revenue",
]


def fetch(lookback_hours: int = 24) -> List[Article]:
    """
    Fetch recent financial news from NewsAPI.

    Parameters
    ----------
    lookback_hours : how far back to search (default 2h matches rolling window)

    Returns
    -------
    List of normalized Article objects
    """
    if not NEWSAPI_KEY or NEWSAPI_KEY == "placeholder":
        logger.warning("[newsapi] NEWSAPI_KEY not set — skipping NewsAPI fetch")
        return []

    articles = []
    from_time = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()

    for query in SEARCH_QUERIES:
        try:
            response = requests.get(
                NEWSAPI_URL,
                params={
                    "q"           : query,
                    "from"        : from_time,
                    "language"    : "en",
                    "sortBy"      : "publishedAt",
                    "pageSize"    : 20,
                    "apiKey"      : NEWSAPI_KEY,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            for item in data.get("articles", []):
                try:
                    article = Article(
                        title        = item.get("title") or "",
                        content      = (item.get("content") or item.get("description") or ""),
                        source       = "newsapi",
                        url          = item.get("url") or "",
                        published_at = _parse_date(item.get("publishedAt")),
                        ticker_hint  = _extract_ticker_hint(item.get("title", "")),
                    )
                    if article.title:
                        articles.append(article)
                except Exception as e:
                    logger.warning(f"[newsapi] Skipping malformed article: {e}")

        except requests.RequestException as e:
            logger.error(f"[newsapi] Request failed for query '{query}': {e}")

    logger.info(f"[newsapi] Fetched {len(articles)} articles")
    return articles


def _parse_date(date_str: str) -> datetime:
    """Parse NewsAPI ISO date string to UTC datetime."""
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def _extract_ticker_hint(title: str) -> str:
    """
    Quick regex pass to grab company names from headline.
    The real NER extraction happens in Module 2 (ner_extractor.py).
    This is just a rough pre-filter hint.
    """
    import re
    # Look for patterns like "TCS", "Infosys", "HDFC Bank" in the title
    # Uppercase sequences of 2–5 chars are likely tickers
    tickers = re.findall(r'\b[A-Z]{2,5}\b', title)
    return tickers[0] if tickers else ""