"""
module3_stock_filter/volume_filter.py
---------------------------------------
Optional filter: checks if today's traded volume is significantly
higher than the 20-day average — a volume spike often confirms
that institutional money is moving into a stock alongside the news.

Requires: Zerodha Kite API key (skipped gracefully if not available).

Rule: volume > FILTER_VOLUME_SPIKE_MULTIPLIER × 20-day avg volume
Default multiplier: 1.5× (configurable in settings.py)
"""

import logging
from typing import Dict, Optional

from config.settings import (
    KITE_API_KEY,
    KITE_ACCESS_TOKEN,
    FILTER_VOLUME_SPIKE_MULTIPLIER,
)
from module3_stock_filter.score_aggregator import AggregatedScore

logger = logging.getLogger(__name__)


def check_volume_spike(ticker: str) -> Optional[bool]:
    """
    Check if ticker has a volume spike today vs 20-day avg.

    Returns
    -------
    True  = volume spike detected (bullish confirmation)
    False = normal volume (no confirmation)
    None  = could not check (Kite not connected)
    """
    if not KITE_API_KEY or KITE_API_KEY == "placeholder":
        return None   # Kite not configured yet

    if not KITE_ACCESS_TOKEN:
        return None   # not logged in

    try:
        from kiteconnect import KiteConnect
        from datetime import datetime, timedelta
        import pandas as pd

        kite = KiteConnect(api_key=KITE_API_KEY)
        kite.set_access_token(KITE_ACCESS_TOKEN)

        # Fetch last 25 days of daily candles
        to_date   = datetime.now()
        from_date = to_date - timedelta(days=25)

        instrument = f"NSE:{ticker}"
        candles = kite.historical_data(
            instrument_token = _get_instrument_token(kite, ticker),
            from_date        = from_date,
            to_date          = to_date,
            interval         = "day",
        )

        if len(candles) < 5:
            return None

        volumes   = [c["volume"] for c in candles]
        today_vol = volumes[-1]
        avg_20d   = sum(volumes[:-1]) / len(volumes[:-1])

        spike = today_vol > (avg_20d * FILTER_VOLUME_SPIKE_MULTIPLIER)

        logger.debug(
            f"[volume] {ticker}: today={today_vol:,} "
            f"avg20d={avg_20d:,.0f} "
            f"ratio={today_vol/avg_20d:.2f}x "
            f"spike={spike}"
        )
        return spike

    except Exception as e:
        logger.debug(f"[volume] Could not check {ticker}: {e}")
        return None


def _get_instrument_token(kite, ticker: str) -> int:
    """Look up NSE instrument token for a ticker symbol."""
    instruments = kite.instruments("NSE")
    for inst in instruments:
        if inst["tradingsymbol"] == ticker:
            return inst["instrument_token"]
    raise ValueError(f"Instrument token not found for {ticker}")


def annotate_volume_spikes(
    aggregated: Dict[str, AggregatedScore]
) -> Dict[str, AggregatedScore]:
    """
    Check volume spikes for all tickers and annotate AggregatedScore.
    Modifies volume_spike field in-place.
    This is optional — stocks without confirmed spikes still proceed.
    """
    if not KITE_API_KEY or KITE_API_KEY == "placeholder":
        logger.info("[volume] Kite not configured — skipping volume check")
        return aggregated

    for ticker, score in aggregated.items():
        spike = check_volume_spike(ticker)
        score.volume_spike = spike
        if spike:
            logger.info(f"[volume] Volume spike confirmed for {ticker}")

    return aggregated