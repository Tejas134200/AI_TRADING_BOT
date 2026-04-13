"""
module2_ai_engine/ticker_mapper.py
------------------------------------
Dynamic Ticker Resolver using custom CSV.
Only allows tickers found in the 'SYMBOL' column of your CSV.
"""

import pandas as pd
import os
import logging
from typing import Optional, Set

logger = logging.getLogger(__name__)

# Path to your CSV file
CSV_PATH = os.path.join(os.getcwd(), "config", "nifty500.csv")

# Internal storage for the whitelist
_VALID_TICKERS: Set[str] = set()

def load_tickers_from_csv():
    """Loads CSV and populates the whitelist from the SYMBOL column."""
    global _VALID_TICKERS
    try:
        if not os.path.exists(CSV_PATH):
            logger.error(f"[mapper] CSV not found at {CSV_PATH}")
            return

        # Read CSV
        df = pd.read_csv(CSV_PATH)
        
        # CLEAN THE HEADERS: Convert all column names to uppercase and strip spaces
        df.columns = [c.strip().upper() for c in df.columns]

        if 'SYMBOL' not in df.columns:
            logger.error(f"[mapper] Critical Error: 'SYMBOL' column not found. Available columns: {list(df.columns)}")
            return

        # Clean the actual data in the SYMBOL column
        symbols = df['SYMBOL'].dropna().unique()
        _VALID_TICKERS = {str(s).strip().upper() for s in symbols}

        logger.info(f"[mapper] Loaded {len(_VALID_TICKERS)} valid symbols from CSV")
    
    except Exception as e:
        logger.error(f"[mapper] Failed to load symbols from CSV: {e}")
# Initial load
load_tickers_from_csv()

def resolve(raw: str) -> Optional[str]:
    """
    Resolve a raw string to a VALID NSE ticker.
    """
    if not raw:
        return None

    # Clean the input (remove $ for cashtags like $TCS)
    cleaned = raw.strip().lstrip("$").upper()

    # 1. Direct Whitelist Check
    # If the word (e.g., RELIANCE) is in our CSV list, return it
    if cleaned in _VALID_TICKERS:
        return cleaned

    # 2. Check if a valid ticker is INSIDE the raw string
    # Useful for "TCS Q3 results" -> find "TCS"
    words = cleaned.split()
    for word in words:
        if word in _VALID_TICKERS:
            return word

    # If it's not in the SYMBOL column, it's rejected (e.g., GDP, EGM, BOARD)
    return None

def resolve_batch(raw_list: list[str]) -> dict[str, Optional[str]]:
    return {raw: resolve(raw) for raw in raw_list}