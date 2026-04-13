"""
module3_stock_filter/filter_engine.py
---------------------------------------
Applies all filtering rules in sequence and produces
the final candidate watchlist.

Filter pipeline:
  All scored tickers
      │
      ├─ [Rule 1] avg_score >= 0.70               sentiment threshold
      ├─ [Rule 2] mention_count >= 1              has coverage
      ├─ [Rule 3] top_sentiment != "negative"     no net-negative stocks
      ├─ [Rule 4] not a non-tradeable entity      skip RBI, SEBI, NIFTY etc.
      ├─ [Rule 5] price reality check             AI sentiment must not
      │           (via yfinance)                  contradict actual price move
      └─ [Rule 6] max FILTER_MAX_WATCHLIST_SIZE   top N by score
      │
      ▼
  Candidate watchlist → Module 4 (technical analysis)
"""

import logging
from typing import Dict, List, Optional

from config.settings import (
    FILTER_MIN_SENTIMENT_SCORE,
    FILTER_MAX_WATCHLIST_SIZE,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# NON-TRADEABLE ENTITIES
# ─────────────────────────────────────────────
# These appear constantly in financial news but are
# indices, regulators, currencies — not buyable stocks.

NON_TRADEABLE = {
    # Indices
    "NIFTY50", "NIFTY", "NIFTY100", "NIFTY500",
    "BANKNIFTY", "FINNIFTY", "MIDCAPNIFTY",
    "SENSEX", "BSE500", "BSE200",
    # Regulators / Govt
    "RBI", "SEBI", "IRDAI", "PFRDA", "AMFI",
    "GOI", "GOVT", "MPC", "PMO", "CBDT", "FIPB",
    # Currencies / Macro
    "RUPEE", "INR", "USD", "EUR", "GBP", "YEN",
    "CPI", "GDP", "WPI", "IIP", "PMI",
    # Exchanges / Orgs
    "NSE", "BSE", "MCX", "NCDEX",
    "IMF", "WB", "OECD", "WHO", "UN", "WTO",
    # Common false positives from news text
    "FII", "FPI", "DII", "MF", "ETF",
    "IPO", "QIP", "OFS", "NFO",
}


# ─────────────────────────────────────────────
# PRICE REALITY CHECK
# ─────────────────────────────────────────────

def _price_reality_check(ticker: str, sentiment: str) -> bool:
    """
    Cross-check AI sentiment against actual price movement.

    Problem this solves:
      FinBERT reads "despite the 400-point fall, analysts expect recovery"
      and scores it POSITIVE because of the word "recovery".
      But the stock actually fell — so it's a false signal.

    Logic:
      - AI says positive but stock fell > 1.5% today → REJECT
      - AI says negative but stock rose > 1.5% today → REJECT
      - Can't fetch data (market closed, holiday) → ALLOW (don't block)

    Parameters
    ----------
    ticker    : NSE ticker e.g. "TCS"
    sentiment : "positive" | "negative" | "neutral"

    Returns
    -------
    True  = sentiment is consistent with price, allow through
    False = sentiment contradicts price, reject this ticker
    """
    # Neutral sentiment never contradicts price
    if sentiment == "neutral":
        return True

    try:
        import yfinance as yf

        symbol = f"{ticker}.NS"
        df = yf.Ticker(symbol).history(period="2d")

        # If we can't get 2 days of data (holiday / bad ticker) — allow through
        if df is None or len(df) < 2:
            logger.debug(f"[reality_check] {ticker}: not enough data — allowing through")
            return True

        prev_close  = df["Close"].iloc[-2]
        today_close = df["Close"].iloc[-1]

        if prev_close == 0:
            return True

        change_pct = ((today_close - prev_close) / prev_close) * 100

        # AI positive but price fell more than 1.5%
        if sentiment == "positive" and change_pct < -1.5:
            logger.info(
                f"[reality_check] REJECTED {ticker}: "
                f"AI=positive but price={change_pct:+.1f}% today"
            )
            return False

        # AI negative but price rose more than 1.5%
        if sentiment == "negative" and change_pct > 1.5:
            logger.info(
                f"[reality_check] REJECTED {ticker}: "
                f"AI=negative but price={change_pct:+.1f}% today"
            )
            return False

        logger.debug(
            f"[reality_check] {ticker}: AI={sentiment} price={change_pct:+.1f}% — consistent"
        )
        return True

    except Exception as e:
        # Never block a stock because of a data fetch failure
        logger.debug(f"[reality_check] {ticker}: check failed ({e}) — allowing through")
        return True


# ─────────────────────────────────────────────
# MAIN FILTER
# ─────────────────────────────────────────────

def apply_rules(aggregated: Dict) -> List:
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
                f"avg_score={score.avg_score:.2f} < min={FILTER_MIN_SENTIMENT_SCORE}"
            )

        # Rule 2: must have at least one mention
        if score.mention_count < 1:
            reasons.append("no mentions")

        # Rule 3: no net-negative stocks
        if score.top_sentiment == "negative" and score.avg_score < 0.4:
            reasons.append(
                f"net_negative: sentiment={score.top_sentiment} "
                f"score={score.avg_score:.2f}"
            )

        # Rule 4: non-tradeable entity check
        if ticker.upper() in NON_TRADEABLE:
            reasons.append("non-tradeable entity (index/regulator/currency)")

        # Only run price check if all other rules passed (saves yfinance calls)
        if not reasons:
            # Rule 5: price reality check
            if not _price_reality_check(ticker, score.top_sentiment):
                reasons.append(
                    f"price contradicts AI sentiment ({score.top_sentiment})"
                )

        if reasons:
            dropped[ticker] = reasons
        else:
            passed.append(score)

    # Log what was dropped and why
    for ticker, reasons in dropped.items():
        logger.info(f"[filter] DROPPED {ticker}: {' | '.join(reasons)}")

    # Sort by avg_score descending, take top N
    passed.sort(key=lambda x: x.avg_score, reverse=True)
    watchlist = passed[:FILTER_MAX_WATCHLIST_SIZE]

    logger.info(
        f"[filter] Result: {len(watchlist)} in watchlist, "
        f"{len(dropped)} dropped from {len(aggregated)} total tickers"
    )

    return watchlist


# ─────────────────────────────────────────────
# REPORT PRINTER
# ─────────────────────────────────────────────

def print_filter_report(aggregated: Dict, watchlist: List):
    """Print a clear table showing what passed and what was dropped."""
    passed_tickers = {s.ticker for s in watchlist}

    print(
        f"\n  {'TICKER':<12} {'SCORE':<8} {'MENTIONS':<10} "
        f"{'SOURCES':<10} {'SENTIMENT':<12} {'STATUS'}"
    )
    print(f"  {'-'*12} {'-'*8} {'-'*10} {'-'*10} {'-'*12} {'-'*12}")

    for ticker, score in aggregated.items():
        status = "✓ WATCHLIST" if ticker in passed_tickers else "✗ dropped"
        print(
            f"  {ticker:<12} {score.avg_score:<8.2f} "
            f"{score.mention_count:<10} {score.source_diversity:<10} "
            f"{score.top_sentiment:<12} {status}"
        )