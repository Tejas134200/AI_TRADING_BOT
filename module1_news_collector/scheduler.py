"""
module1_news_collector/scheduler.py
-------------------------------------
Main orchestrator for Module 1.

Runs every 5 minutes (configurable via NEWS_FETCH_INTERVAL_SECONDS).
Calls all enabled fetchers → deduplicates → saves to MySQL → pushes
fresh articles to Redis queue for Module 2 to consume.

Run this directly to start the news collection loop:
    python -m module1_news_collector.scheduler
"""

import json
import logging
import sys
import time
from datetime import datetime
from typing import List

from config.settings import (
    NEWS_FETCH_INTERVAL_SECONDS,
    NEWS_SOURCES,
    REDIS_NEWS_QUEUE_KEY,
    validate,
)
from module1_news_collector.deduplicator import Deduplicator
from module1_news_collector.normalizer import Article

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers= [logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# FETCH CYCLE
# ─────────────────────────────────────────────

def run_fetch_cycle() -> List[Article]:
    """
    Run one full fetch cycle across all enabled sources.
    Returns fresh (deduplicated) articles.
    """
    all_articles: List[Article] = []

    if "newsapi" in NEWS_SOURCES:
        try:
            from module1_news_collector.newsapi_fetcher import fetch as fetch_newsapi
            all_articles += fetch_newsapi()
        except Exception as e:
            logger.error(f"[scheduler] NewsAPI fetch error: {e}")

    if "google_news" in NEWS_SOURCES:
        try:
            from module1_news_collector.google_news_fetcher import fetch as fetch_google
            all_articles += fetch_google()
        except Exception as e:
            logger.error(f"[scheduler] Google News fetch error: {e}")

    if "nse_bse" in NEWS_SOURCES:
        try:
            from module1_news_collector.nse_bse_scraper import fetch as fetch_nse
            all_articles += fetch_nse()
        except Exception as e:
            logger.error(f"[scheduler] NSE/BSE fetch error: {e}")

    if "twitter" in NEWS_SOURCES:
        try:
            from module1_news_collector.twitter_fetcher import fetch as fetch_twitter
            all_articles += fetch_twitter()
        except Exception as e:
            logger.error(f"[scheduler] Twitter fetch error: {e}")

    logger.info(f"[scheduler] Total fetched: {len(all_articles)} articles across all sources")

    # Deduplicate
    dedup = Deduplicator()
    fresh = dedup.filter(all_articles)
    logger.info(f"[scheduler] Fresh (new) articles: {len(fresh)}")

    return fresh


def save_to_db(articles: List[Article]):
    """Persist fresh articles to MySQL articles table."""
    if not articles:
        return
    try:
        from database.models import Article as ArticleModel
        from database.connection import get_db

        with get_db() as db:
            for a in articles:
                exists = db.query(ArticleModel).filter_by(hash=a.hash).first()
                if not exists:
                    row = ArticleModel(
                        hash         = a.hash,
                        title        = a.title,
                        content      = a.content,
                        source       = a.source,
                        url          = a.url,
                        published_at = a.published_at,
                        ticker_hint  = a.ticker_hint,
                        fetched_at   = a.fetched_at,
                    )
                    db.add(row)
        logger.info(f"[scheduler] Saved {len(articles)} articles to MySQL")
    except Exception as e:
        logger.error(f"[scheduler] DB save failed: {e}")


def push_to_queue(articles: List[Article]):
    """Push fresh articles to Redis queue for Module 2 to consume."""
    if not articles:
        return
    try:
        import redis as redis_lib
        from config.settings import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB

        r = redis_lib.Redis(
            host=REDIS_HOST, port=REDIS_PORT,
            password=REDIS_PASSWORD or None, db=REDIS_DB,
            decode_responses=True,
        )
        for article in articles:
            r.rpush(REDIS_NEWS_QUEUE_KEY, json.dumps(article.to_dict()))

        logger.info(f"[scheduler] Pushed {len(articles)} articles to Redis queue")
    except Exception as e:
        # Redis not available — log and continue (articles are still in MySQL)
        logger.warning(f"[scheduler] Redis push failed (non-fatal): {e}")


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

def start():
    """Start the news collection loop. Runs indefinitely."""
    validate()   # checks .env before first cycle
    logger.info(
        f"[scheduler] News collector started. "
        f"Interval: {NEWS_FETCH_INTERVAL_SECONDS}s | "
        f"Sources: {NEWS_SOURCES}"
    )

    while True:
        cycle_start = datetime.utcnow()
        logger.info(f"[scheduler] ── Cycle start: {cycle_start.strftime('%H:%M:%S')} ──")

        try:
            fresh_articles = run_fetch_cycle()
            save_to_db(fresh_articles)
            push_to_queue(fresh_articles)
        except Exception as e:
            logger.error(f"[scheduler] Cycle failed: {e}", exc_info=True)

        elapsed = (datetime.utcnow() - cycle_start).total_seconds()
        sleep_for = max(0, NEWS_FETCH_INTERVAL_SECONDS - elapsed)
        logger.info(f"[scheduler] Cycle done in {elapsed:.1f}s. Sleeping {sleep_for:.0f}s...\n")
        time.sleep(sleep_for)


if __name__ == "__main__":
    start()