"""
module3_stock_filter/score_aggregator.py
-----------------------------------------
Aggregates all ScoredArticle rows for each ticker
over the rolling 2-hour window and computes:
  - avg_sentiment_score  (mean of all article final_scores)
  - mention_count        (how many distinct articles mention this ticker)
  - source_diversity     (how many distinct sources — newsapi, google_news etc.)
  - score_trend          (is score improving or declining over the window?)

Why rolling 2 hours?
  Market moves fast. A news article from 3 hours ago is stale —
  the price has already reacted. We only care about what's happening NOW.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AggregatedScore:
    ticker           : str
    exchange         : str
    avg_score        : float        # mean final_score across all articles
    mention_count    : int          # number of distinct articles
    source_diversity : int          # number of distinct sources
    score_trend      : float        # positive = improving, negative = declining
    top_sentiment    : str          # most common sentiment label
    window_start     : datetime
    window_end       : datetime
    article_scores   : List[float] = field(default_factory=list)

    def __repr__(self):
        return (
            f"<AggregatedScore ticker={self.ticker} "
            f"avg={self.avg_score:.2f} mentions={self.mention_count} "
            f"sources={self.source_diversity} trend={self.score_trend:+.2f}>"
        )


def aggregate(window_hours: int = 2) -> Dict[str, AggregatedScore]:
    from database.models import ScoredArticle, Article
    from database.connection import get_db

    window_start = datetime.utcnow() - timedelta(hours=window_hours)
    window_end   = datetime.utcnow()

    results: Dict[str, AggregatedScore] = {}
    ticker_data: Dict[str, dict] = {} # Initialize outside to use later
    total_rows = 0

    try:
        with get_db() as db:
            rows = (
                db.query(ScoredArticle, Article)
                .join(Article, ScoredArticle.article_id == Article.id)
                .filter(ScoredArticle.analyzed_at >= window_start)
                .all()
            )

            if not rows:
                logger.info("[aggregator] No scored articles in window")
                return {}

            total_rows = len(rows)

            # --- MOVE GROUPING LOGIC INSIDE THE 'WITH' BLOCK ---
            for scored, article in rows:
                t = scored.ticker
                if t not in ticker_data:
                    ticker_data[t] = {
                        "exchange"   : scored.exchange,
                        "scores"     : [],
                        "sentiments" : [],
                        "sources"    : set(),
                    }
                # Accessing these attributes while 'db' session is alive
                ticker_data[t]["scores"].append(scored.final_score)
                ticker_data[t]["sentiments"].append(scored.sentiment)
                ticker_data[t]["sources"].add(article.source)
            # --- END OF INSIDE THE 'WITH' BLOCK ---

        # Build AggregatedScore per ticker (Safe outside now because we have plain lists)
        for ticker, data in ticker_data.items():
            scores = data["scores"]
            avg    = round(sum(scores) / len(scores), 4)

            mid   = len(scores) // 2
            trend = 0.0
            if mid > 0:
                first_half  = sum(scores[:mid]) / mid
                second_half = sum(scores[mid:]) / (len(scores) - mid)
                trend = round(second_half - first_half, 4)

            top_sentiment = max(
                set(data["sentiments"]),
                key=data["sentiments"].count
            )

            results[ticker] = AggregatedScore(
                ticker           = ticker,
                exchange         = data["exchange"],
                avg_score        = avg,
                mention_count    = len(scores),
                source_diversity = len(data["sources"]),
                score_trend      = trend,
                top_sentiment    = top_sentiment,
                window_start     = window_start,
                window_end       = window_end,
                article_scores   = scores,
            )

        logger.info(
            f"[aggregator] {len(results)} tickers aggregated "
            f"from {total_rows} articles in last {window_hours}h"
        )

    except Exception as e:
        logger.error(f"[aggregator] DB query failed: {e}")

    return dict(sorted(results.items(), key=lambda x: x[1].avg_score, reverse=True))