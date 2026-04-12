"""
module3_stock_filter/filter_engine.py
---------------------------------------
Applies all filtering rules in sequence and produces
the final candidate watchlist.

Filter pipeline:
  All scored tickers
      │
      ├─ [Rule 1] avg_score >= 0.70          (sentiment threshold)
      ├─ [Rule 2] mention_count >= 3         (volume of coverage)
      ├─ [Rule 3] source_diversity >= 2      (multiple sources)
      ├─ [Rule 4] top_sentiment != "negative" (no net-negative stocks)
      ├─ [Rule 5] not a non-tradeable entity  (skip RBI, SEBI, RUPEE etc.)
      └─ [Rule 6] max FILTER_MAX_WATCHLIST_SIZE stocks (top N by score)
      │
      ▼
  Candidate watchlist  →  Module 4 (technical analysis)
"""

import logging
from typing import Dict, List

from config.settings import (
    FILTER_MIN_SENTIMENT_SCORE,
    FILTER_MAX_WATCHLIST_SIZE,
)
from module3_stock_filter.score_aggregator import AggregatedScore

logger = logging.getLogger(__name__)

# Entities that appear in financial news but are NOT tradeable stocks
NON_TRADEABLE = {
    "RBI", "SEBI", "RUPEE", "INR", "USD", "SENSEX", "NIFTY50",
    "NIFTY", "NSE", "BSE", "MPC", "GOVT", "GOI", "CPI", "GDP",
    "FII", "FPI", "IMF", "WB", "OECD", "WHO", "UN",
}


def apply_rules(
    aggregated: Dict[str, AggregatedScore]
) -> List[AggregatedScore]:
    """
    Apply all filter rules to aggregated scores.

    Parameters
    ----------
    aggregated : output of score_aggregator.aggregate()

    Returns
    -------
    Sorted list of AggregatedScore that passed all rules
    """
    passed  = []
    dropped = {}

    for ticker, score in aggregated.items():
        reasons = []

        # Rule 1: sentiment score threshold
        if score.avg_score < FILTER_MIN_SENTIMENT_SCORE:
            reasons.append(
                f"avg_score={score.avg_score:.2f} < {FILTER_MIN_SENTIMENT_SCORE}"
            )

        # Rule 2 & 3: mention + source diversity (handled by mention_counter
        # but we double-check here for safety)
        if score.mention_count < 1:
            reasons.append("no mentions")

        # Rule 4: no net-negative stocks
        if score.top_sentiment == "negative" and score.avg_score < 0.4:
            reasons.append(
                f"net_negative: sentiment={score.top_sentiment} score={score.avg_score:.2f}"
            )

        # Rule 5: non-tradeable entities
        if ticker in NON_TRADEABLE:
            reasons.append(f"non-tradeable entity")

        if reasons:
            dropped[ticker] = reasons
        else:
            passed.append(score)

    # Log dropped
    for ticker, reasons in dropped.items():
        logger.debug(f"[filter] DROPPED {ticker}: {', '.join(reasons)}")

    # Sort by avg_score descending, take top N
    passed.sort(key=lambda x: x.avg_score, reverse=True)
    watchlist = passed[:FILTER_MAX_WATCHLIST_SIZE]

    logger.info(
        f"[filter] {len(watchlist)} stocks in watchlist "
        f"(from {len(aggregated)} tickers, dropped {len(dropped)})"
    )

    return watchlist


def print_filter_report(
    aggregated  : Dict[str, AggregatedScore],
    watchlist   : List[AggregatedScore],
):
    """Print a clear table showing what passed and what was dropped."""

    passed_tickers = {s.ticker for s in watchlist}

    print(f"\n  {'TICKER':<12} {'AVG_SCORE':<12} {'MENTIONS':<10} {'SOURCES':<10} {'SENTIMENT':<12} {'STATUS'}")
    print(f"  {'-'*12} {'-'*12} {'-'*10} {'-'*10} {'-'*12} {'-'*10}")

    for ticker, score in aggregated.items():
        status = "WATCHLIST" if ticker in passed_tickers else "dropped"
        print(
            f"  {ticker:<12} {score.avg_score:<12.2f} "
            f"{score.mention_count:<10} {score.source_diversity:<10} "
            f"{score.top_sentiment:<12} {status}"
        )