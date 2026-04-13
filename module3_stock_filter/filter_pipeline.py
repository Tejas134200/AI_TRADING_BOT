"""
module3_stock_filter/filter_pipeline.py
-----------------------------------------
Main orchestrator for Module 3.

Full pipeline:
  MySQL scored_articles (last 2h)
        ↓
  score_aggregator   →  group by ticker, compute avg/trend
        ↓
  mention_counter    →  drop tickers with < 3 mentions
        ↓
  volume_filter      →  annotate volume spikes (optional)
        ↓
  filter_engine      →  apply score/sentiment/non-tradeable rules
        ↓
  watchlist_manager  →  save to MySQL + Redis
        ↓
  Candidate watchlist  →  Module 4

Run directly:
    python -m module3_stock_filter.filter_pipeline
"""

import logging
import sys

logger = logging.getLogger(__name__)

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers= [logging.StreamHandler(sys.stdout)],
)


def run() -> list:
    """
    Execute the full Module 3 filter pipeline.
    Returns the final watchlist as a list of AggregatedScore.
    """
    from config.settings import FILTER_ROLLING_WINDOW_HOURS
    from module3_stock_filter.score_aggregator import aggregate
    from module3_stock_filter.mention_counter import filter_by_mentions
    from module3_stock_filter.volume_filter import annotate_volume_spikes
    from module3_stock_filter.filter_engine import apply_rules, print_filter_report
    from module3_stock_filter.watchlist_manager import save_watchlist

    logger.info("[module3] Starting stock filter pipeline...")

    # Step 1: Aggregate scores from MySQL
    aggregated = aggregate(window_hours=FILTER_ROLLING_WINDOW_HOURS)
    if not aggregated:
        logger.warning("[module3] No scored articles found — nothing to filter")
        return []

    logger.info(f"[module3] Step 1 done: {len(aggregated)} tickers aggregated")

    # Step 2: Filter by mention count
    after_mentions = filter_by_mentions(aggregated)
    logger.info(f"[module3] Step 2 done: {len(after_mentions)} tickers after mention filter")

    # Step 3: Annotate volume spikes (skipped if Kite not configured)
    after_volume = annotate_volume_spikes(after_mentions)

    # Step 4: Apply all scoring rules → final watchlist
    watchlist = apply_rules(after_volume)
    logger.info(f"[module3] Step 4 done: {len(watchlist)} stocks in final watchlist")

    # Step 5: Save to MySQL + Redis
    save_watchlist(watchlist)

    return watchlist


if __name__ == "__main__":
    from module3_stock_filter.filter_engine import print_filter_report
    from module3_stock_filter.score_aggregator import aggregate
    from config.settings import FILTER_ROLLING_WINDOW_HOURS

    print("\n" + "=" * 65)
    print("   MODULE 3 — Stock Filter Pipeline")
    print("=" * 65)

    watchlist  = run()
    aggregated = aggregate(window_hours=FILTER_ROLLING_WINDOW_HOURS)

    print(f"\n{'='*65}")
    print(f"  FILTER REPORT  (all tickers seen in last {FILTER_ROLLING_WINDOW_HOURS}h)")
    print(f"{'='*65}")
    print_filter_report(aggregated, watchlist)

    print(f"\n{'='*65}")
    print(f"  FINAL WATCHLIST  →  {len(watchlist)} stocks passing to Module 4")
    print(f"{'='*65}")

    if watchlist:
        print(f"\n  {'#':<4} {'TICKER':<12} {'SCORE':<8} {'MENTIONS':<10} {'TREND':<10} {'SENTIMENT'}")
        print(f"  {'-'*4} {'-'*12} {'-'*8} {'-'*10} {'-'*10} {'-'*10}")
        for i, s in enumerate(watchlist, 1):
            trend_arrow = "↑" if s.score_trend > 0 else ("↓" if s.score_trend < 0 else "→")
            print(
                f"  {i:<4} {s.ticker:<12} {s.avg_score:<8.2f} "
                f"{s.mention_count:<10} {trend_arrow} {s.score_trend:+.2f}   "
                f"{s.top_sentiment}"
            )
        print(f"\n  These tickers saved to MySQL watchlist table + Redis filter:watchlist")
        print(f"  Module 4 will now run technical analysis on each.")
    else:
        print("\n  No stocks passed all filters this cycle.")
        print("  This is normal — the market may be quiet or news coverage is low.")
        print("  Module 1 + 2 will keep running and the next cycle may produce candidates.")

    print(f"\n{'='*65}\n")