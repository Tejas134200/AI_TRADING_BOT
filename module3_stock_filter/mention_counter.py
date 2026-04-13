"""
module3_stock_filter/mention_counter.py
-----------------------------------------
Checks if a ticker has enough mention volume to be significant.

Why this matters:
  A single article saying "TCS might rally" is noise.
  Five articles from three different sources saying the same thing
  is a real signal worth acting on.

Rules applied here:
  - mention_count  >= FILTER_MIN_MENTION_COUNT  (default 3)
  - source_diversity >= 2  (at least 2 different sources confirm it)
    prevents one biased source from triggering trades
"""

import logging
from typing import Dict, List

from config.settings import FILTER_MIN_MENTION_COUNT
from config.settings import MIN_SOURCE_DIVERSITY
from module3_stock_filter.score_aggregator import AggregatedScore

logger = logging.getLogger(__name__)

  # at least 2 distinct sources must mention the stock


def filter_by_mentions(
    aggregated: Dict[str, AggregatedScore]
) -> Dict[str, AggregatedScore]:
    """
    Keep only tickers that meet minimum mention thresholds.

    Parameters
    ----------
    aggregated : output of score_aggregator.aggregate()

    Returns
    -------
    Filtered dict of ticker → AggregatedScore
    """
    passed  = {}
    dropped = {}

    for ticker, score in aggregated.items():
        reasons = []

        if score.mention_count < FILTER_MIN_MENTION_COUNT:
            reasons.append(
                f"mentions={score.mention_count} < min={FILTER_MIN_MENTION_COUNT}"
            )

        if score.source_diversity < MIN_SOURCE_DIVERSITY:
            reasons.append(
                f"sources={score.source_diversity} < min={MIN_SOURCE_DIVERSITY}"
            )

        if reasons:
            dropped[ticker] = reasons
        else:
            passed[ticker] = score

    # Log summary
    for ticker, reasons in dropped.items():
        logger.debug(f"[mentions] DROPPED {ticker}: {', '.join(reasons)}")

    logger.info(
        f"[mentions] {len(passed)} passed, {len(dropped)} dropped by mention filter"
    )

    return passed


def get_mention_summary(aggregated: Dict[str, AggregatedScore]) -> List[dict]:
    """Return a list of dicts summarizing mention counts — useful for logging."""
    return [
        {
            "ticker"    : s.ticker,
            "mentions"  : s.mention_count,
            "sources"   : s.source_diversity,
            "avg_score" : s.avg_score,
        }
        for s in aggregated.values()
    ]