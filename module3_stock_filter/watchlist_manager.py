"""
module3_stock_filter/watchlist_manager.py
-------------------------------------------
Saves the final watchlist to MySQL and Redis.

MySQL  →  watchlist table  (permanent audit trail)
Redis  →  filter:watchlist  sorted set  (Module 4 reads from here)

Redis sorted set structure:
  Key   : "filter:watchlist"
  Member: ticker symbol (e.g. "TCS")
  Score : composite avg_score (e.g. 0.87)

Module 4 reads:
  ZREVRANGEBYSCORE filter:watchlist 1.0 0.0  → ranked list of tickers
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List

from config.settings import (
    REDIS_WATCHLIST_KEY,
    FILTER_ROLLING_WINDOW_HOURS,
)
from module3_stock_filter.score_aggregator import AggregatedScore

logger = logging.getLogger(__name__)


def save_watchlist(candidates: List[AggregatedScore]):
    """
    Save watchlist to both MySQL and Redis.

    Parameters
    ----------
    candidates : filtered list from filter_engine.apply_rules()
    """
    if not candidates:
        logger.info("[watchlist] No candidates to save")
        return

    _save_to_mysql(candidates)
    _save_to_redis(candidates)


def _save_to_mysql(candidates: List[AggregatedScore]):
    """Persist watchlist entries to MySQL watchlist table."""
    try:
        from database.models import WatchlistEntry
        from database.connection import get_db

        saved = 0
        with get_db() as db:
            for score in candidates:
                # Mark any previous active entry for this ticker as expired
                db.query(WatchlistEntry).filter_by(
                    ticker=score.ticker,
                    status="active"
                ).update({"status": "expired"})

                # Insert new active entry
                entry = WatchlistEntry(
                    ticker        = score.ticker,
                    exchange      = score.exchange,
                    avg_sentiment = score.avg_score,
                    mention_count = score.mention_count,
                    volume_spike  = getattr(score, "volume_spike", False) or False,
                    status        = "active",
                    window_start  = score.window_start,
                    window_end    = score.window_end,
                )
                db.add(entry)
                saved += 1

        logger.info(f"[watchlist] Saved {saved} entries to MySQL watchlist table")

    except Exception as e:
        logger.error(f"[watchlist] MySQL save failed: {e}")


def _save_to_redis(candidates: List[AggregatedScore]):
    """
    Save watchlist to Redis sorted set.
    Score = avg_sentiment_score so Module 4 can pop highest-scored first.
    """
    try:
        import redis as redis_lib
        from config.settings import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB

        r = redis_lib.Redis(
            host=REDIS_HOST, port=REDIS_PORT,
            password=REDIS_PASSWORD or None,
            db=REDIS_DB, decode_responses=True,
        )

        # Clear old watchlist
        r.delete(REDIS_WATCHLIST_KEY)

        # Add each ticker with its score
        pipe = r.pipeline()
        for score in candidates:
            # Store full details as JSON string in a separate key
            detail_key = f"watchlist:detail:{score.ticker}"
            pipe.setex(
                detail_key,
                3600,   # 1 hour TTL
                json.dumps({
                    "ticker"          : score.ticker,
                    "exchange"        : score.exchange,
                    "avg_score"       : score.avg_score,
                    "mention_count"   : score.mention_count,
                    "source_diversity": score.source_diversity,
                    "top_sentiment"   : score.top_sentiment,
                    "score_trend"     : score.score_trend,
                })
            )
            # Add to sorted set with score
            pipe.zadd(REDIS_WATCHLIST_KEY, {score.ticker: score.avg_score})

        # Set TTL on the sorted set itself
        pipe.expire(REDIS_WATCHLIST_KEY, 3600)
        pipe.execute()

        logger.info(
            f"[watchlist] Saved {len(candidates)} tickers to Redis "
            f"key: {REDIS_WATCHLIST_KEY}"
        )

    except Exception as e:
        logger.warning(f"[watchlist] Redis save failed (non-fatal): {e}")


def get_active_watchlist() -> List[dict]:
    """
    Read current watchlist from Redis (fastest path).
    Falls back to MySQL if Redis unavailable.
    """
    try:
        import redis as redis_lib
        from config.settings import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB

        r = redis_lib.Redis(
            host=REDIS_HOST, port=REDIS_PORT,
            password=REDIS_PASSWORD or None,
            db=REDIS_DB, decode_responses=True,
        )
        # Get tickers ranked by score (highest first)
        tickers = r.zrevrangebyscore(REDIS_WATCHLIST_KEY, 1.0, 0.0, withscores=True)

        result = []
        for ticker, score in tickers:
            detail_key = f"watchlist:detail:{ticker}"
            detail_raw = r.get(detail_key)
            if detail_raw:
                detail = json.loads(detail_raw)
            else:
                detail = {"ticker": ticker, "avg_score": score}
            result.append(detail)

        return result

    except Exception:
        # Fallback to MySQL
        return _get_watchlist_from_mysql()


def _get_watchlist_from_mysql() -> List[dict]:
    try:
        from database.models import WatchlistEntry
        from database.connection import get_db

        with get_db() as db:
            entries = (
                db.query(WatchlistEntry)
                .filter_by(status="active")
                .order_by(WatchlistEntry.avg_sentiment.desc())
                .all()
            )
            return [
                {
                    "ticker"       : e.ticker,
                    "avg_score"    : e.avg_sentiment,
                    "mention_count": e.mention_count,
                    "status"       : e.status,
                }
                for e in entries
            ]
    except Exception as e:
        logger.error(f"[watchlist] MySQL fallback failed: {e}")
        return []