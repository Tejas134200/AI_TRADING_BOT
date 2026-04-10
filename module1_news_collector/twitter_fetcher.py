"""
module1_news_collector/twitter_fetcher.py
------------------------------------------
Optional — fetches finance-related tweets via Twitter API v2.

Requires: TWITTER_BEARER_TOKEN in .env
Enable by adding "twitter" to NEWS_SOURCES in settings.py

Tracks:
  - $TICKER cashtags (e.g. $TCS, $INFY, $RELIANCE)
  - Key finance accounts (@NSEIndia, @SEBI_India)
  - Breaking news keywords
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List

from config.settings import TWITTER_BEARER_TOKEN
from module1_news_collector.normalizer import Article

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    "$TCS OR $INFY OR $RELIANCE OR $HDFCBANK lang:en",
    "$WIPRO OR $ICICIBANK OR $SBIN OR $LT lang:en",
    "NSE India results acquisition merger lang:en -is:retweet",
]


def fetch() -> List[Article]:
    """
    Search recent tweets for Indian stock signals.
    Returns list of Article objects.
    Silently skips if TWITTER_BEARER_TOKEN is not configured.
    """
    if not TWITTER_BEARER_TOKEN:
        logger.debug("[twitter] TWITTER_BEARER_TOKEN not set — skipping")
        return []

    try:
        import tweepy
    except ImportError:
        logger.warning("[twitter] tweepy not installed. Run: pip install tweepy")
        return []

    articles = []
    client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN, wait_on_rate_limit=True)
    start_time = datetime.now(timezone.utc) - timedelta(hours=2)

    for query in SEARCH_QUERIES:
        try:
            response = client.search_recent_tweets(
                query        = query,
                start_time   = start_time,
                max_results  = 20,
                tweet_fields = ["created_at", "text", "author_id"],
            )
            if not response.data:
                continue

            for tweet in response.data:
                article = Article(
                    title        = tweet.text[:200],
                    content      = tweet.text,
                    source       = "twitter",
                    url          = f"https://twitter.com/i/web/status/{tweet.id}",
                    published_at = tweet.created_at.replace(tzinfo=None),
                    ticker_hint  = _extract_cashtag(tweet.text),
                )
                articles.append(article)

        except Exception as e:
            logger.error(f"[twitter] Query failed '{query}': {e}")

    logger.info(f"[twitter] Fetched {len(articles)} tweets")
    return articles


def _extract_cashtag(text: str) -> str:
    """Extract first $TICKER cashtag from tweet text."""
    import re
    match = re.search(r'\$([A-Z]{2,10})', text)
    return match.group(1) if match else ""