"""
module3_stock_filter/volume_filter.py
---------------------------------------
Checks if today's traded volume is significantly higher than the 
20-day average using yfinance (Free, no API key required).

Rule: volume > FILTER_VOLUME_SPIKE_MULTIPLIER × 20-day avg volume
"""

import logging
from typing import Dict, Optional
import yfinance as yf
from datetime import datetime, timedelta

from config.settings import (
    FILTER_VOLUME_SPIKE_MULTIPLIER,
)
from module3_stock_filter.score_aggregator import AggregatedScore

logger = logging.getLogger(__name__)

def check_volume_spike(ticker: str) -> Optional[bool]:
    """
    Check if ticker has a volume spike today vs 20-day avg using yfinance.

    Returns
    -------
    True  = volume spike detected
    False = normal volume
    None  = could not check (network error or ticker not found)
    """
    try:
        # yfinance needs .NS for National Stock Exchange (India)
        symbol = f"{ticker}.NS"
        stock = yf.Ticker(symbol)
        
        # Fetch last 30 days to ensure we get 20 solid trading days
        df = stock.history(period="30d")

        if df.empty or len(df) < 5:
            logger.debug(f"[volume] Not enough data for {symbol}")
            return None

        # Get volumes
        # df['Volume'] contains the daily volume
        volumes = df['Volume'].tolist()
        
        today_vol = volumes[-1]
        # Calculate average of the previous 20 trading days
        available = min(20, len(volumes) - 1)
        avg_20d = sum(volumes[-available-1:-1]) / available

        if avg_20d == 0:
            return False

        spike = today_vol > (avg_20d * FILTER_VOLUME_SPIKE_MULTIPLIER)

        logger.debug(
            f"[volume] {ticker}: today={today_vol:,.0f} "
            f"avg20d={avg_20d:,.0f} "
            f"ratio={today_vol/avg_20d:.2f}x "
            f"spike={spike}"
        )
        return spike

    except Exception as e:
        logger.error(f"[volume] Error checking {ticker} via yfinance: {e}")
        return None

def annotate_volume_spikes(
    aggregated: Dict[str, AggregatedScore]
) -> Dict[str, AggregatedScore]:
    """
    Check volume spikes for all tickers and annotate AggregatedScore.
    """
    logger.info(f"[volume] Checking volume spikes for {len(aggregated)} tickers...")
    
    for ticker, score in aggregated.items():
        spike = check_volume_spike(ticker)
        score.volume_spike = spike
        if spike:
            logger.info(f"[volume] 🔥 Volume spike confirmed for {ticker}")
        else:
            logger.debug(f"[volume] No spike for {ticker}")

    return aggregated