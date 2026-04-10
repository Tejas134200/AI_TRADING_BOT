"""
module1_news_collector/deduplicator.py
---------------------------------------
Redis-based deduplication.

Before any article is pushed to the AI engine queue, its hash is
checked here. If we've seen it in the last 4 hours, it's dropped.
This prevents the same Breaking News article from being re-analyzed
every time the cron job runs.

Works without Redis too — falls back to an in-memory set so you
can develop locally without a Redis instance running.
"""

import logging
from typing import List

from module1_news_collector.normalizer import Article

logger = logging.getLogger(__name__)


class Deduplicator:
    """
    Checks and registers article hashes.

    Usage
    -----
        dedup = Deduplicator()          # auto-detects Redis or falls back to memory
        fresh = dedup.filter(articles)  # returns only unseen articles
    """

    def __init__(self):
        self._redis = None
        self._memory_seen: set = set()   # fallback when Redis is unavailable
        self._ttl: int = 0
        self._prefix: str = ""
        self._use_redis = False

        self._connect()

    def _connect(self):
        try:
            import redis as redis_lib
            from config.settings import (
                REDIS_HOST, REDIS_PORT, REDIS_PASSWORD,
                REDIS_DB, REDIS_DEDUP_PREFIX, REDIS_DEDUP_TTL_SECONDS
            )
            self._redis = redis_lib.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD or None,
                db=REDIS_DB,
                socket_connect_timeout=2,
                decode_responses=True,
            )
            self._redis.ping()   # raises if unreachable
            self._ttl = REDIS_DEDUP_TTL_SECONDS
            self._prefix = REDIS_DEDUP_PREFIX
            self._use_redis = True
            logger.info("[dedup] Connected to Redis — using Redis deduplication")

        except Exception as e:
            logger.warning(
                f"[dedup] Redis unavailable ({e}). "
                "Falling back to in-memory deduplication (resets on restart)."
            )
            self._use_redis = False

    def is_seen(self, article: Article) -> bool:
        """Return True if this article hash has been seen before."""
        if self._use_redis:
            return self._redis.exists(f"{self._prefix}{article.hash}") == 1
        return article.hash in self._memory_seen

    def mark_seen(self, article: Article):
        """Register this article as seen."""
        if self._use_redis:
            key = f"{self._prefix}{article.hash}"
            self._redis.setex(key, self._ttl, "1")
        else:
            self._memory_seen.add(article.hash)

    def filter(self, articles: List[Article]) -> List[Article]:
        """
        Return only articles not seen before, and mark them as seen.

        Example
        -------
            fresh = dedup.filter(fetched_articles)
            # fresh contains only new articles — safe to push to queue
        """
        fresh = []
        for article in articles:
            if self.is_seen(article):
                logger.debug(f"[dedup] Skipping duplicate: {article.title[:60]}...")
            else:
                self.mark_seen(article)
                fresh.append(article)

        dropped = len(articles) - len(fresh)
        if dropped:
            logger.info(f"[dedup] Dropped {dropped} duplicates, {len(fresh)} fresh articles")

        return fresh