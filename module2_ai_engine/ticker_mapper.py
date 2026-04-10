"""
module2_ai_engine/ticker_mapper.py
------------------------------------
Resolves raw company names / partial names / cashtags
to official NSE ticker symbols.

Examples
--------
    "Tata Consultancy"  →  "TCS"
    "tcs"               →  "TCS"
    "HDFC Bank"         →  "HDFCBANK"
    "$INFY"             →  "INFY"
    "Reliance"          →  "RELIANCE"
"""

import re
from typing import Optional


# ─────────────────────────────────────────────
# MASTER LOOKUP TABLE
# company aliases / partial names → NSE ticker
# Add more as needed
# ─────────────────────────────────────────────

TICKER_MAP: dict[str, str] = {
    # IT
    "tcs": "TCS",
    "tata consultancy": "TCS",
    "tata consultancy services": "TCS",
    "infosys": "INFY",
    "infy": "INFY",
    "wipro": "WIPRO",
    "hcl": "HCLTECH",
    "hcl tech": "HCLTECH",
    "hcl technologies": "HCLTECH",
    "tech mahindra": "TECHM",
    "mphasis": "MPHASIS",
    "ltimindtree": "LTIM",
    "lti mindtree": "LTIM",
    "persistent": "PERSISTENT",
    "coforge": "COFORGE",

    # Banking
    "hdfc bank": "HDFCBANK",
    "hdfcbank": "HDFCBANK",
    "hdfc": "HDFCBANK",
    "icici bank": "ICICIBANK",
    "icici": "ICICIBANK",
    "sbi": "SBIN",
    "state bank": "SBIN",
    "state bank of india": "SBIN",
    "axis bank": "AXISBANK",
    "kotak": "KOTAKBANK",
    "kotak mahindra": "KOTAKBANK",
    "kotak bank": "KOTAKBANK",
    "indusind": "INDUSINDBK",
    "indusind bank": "INDUSINDBK",
    "yes bank": "YESBANK",
    "bandhan": "BANDHANBNK",
    "federal bank": "FEDERALBNK",
    "idfc": "IDFCFIRSTB",

    # FMCG
    "hindustan unilever": "HINDUNILVR",
    "hul": "HINDUNILVR",
    "itc": "ITC",
    "nestle": "NESTLEIND",
    "britannia": "BRITANNIA",
    "dabur": "DABUR",
    "marico": "MARICO",
    "godrej consumer": "GODREJCP",
    "colgate": "COLPAL",
    "emami": "EMAMILTD",

    # Auto
    "maruti": "MARUTI",
    "maruti suzuki": "MARUTI",
    "tata motors": "TATAMOTORS",
    "m&m": "M&M",
    "mahindra": "M&M",
    "mahindra & mahindra": "M&M",
    "bajaj auto": "BAJAJ-AUTO",
    "hero motocorp": "HEROMOTOCO",
    "hero moto": "HEROMOTOCO",
    "eicher": "EICHERMOT",
    "royal enfield": "EICHERMOT",
    "tvs motor": "TVSMOTOR",
    "ashok leyland": "ASHOKLEY",

    # Energy / Oil
    "reliance": "RELIANCE",
    "reliance industries": "RELIANCE",
    "ril": "RELIANCE",
    "ongc": "ONGC",
    "bpcl": "BPCL",
    "ioc": "IOC",
    "indian oil": "IOC",
    "hpcl": "HPCL",
    "gail": "GAIL",
    "petronet": "PETRONET",
    "oil india": "OIL",

    # Pharma
    "sun pharma": "SUNPHARMA",
    "sun pharmaceutical": "SUNPHARMA",
    "dr reddy": "DRREDDY",
    "dr. reddy": "DRREDDY",
    "cipla": "CIPLA",
    "divi's": "DIVISLAB",
    "divis": "DIVISLAB",
    "biocon": "BIOCON",
    "aurobindo": "AUROPHARMA",
    "lupin": "LUPIN",
    "torrent pharma": "TORNTPHARM",
    "alkem": "ALKEM",
    "Abbott": "ABBOTINDIA",

    # Infra / Metals
    "tata steel": "TATASTEEL",
    "jsw steel": "JSWSTEEL",
    "hindalco": "HINDALCO",
    "vedanta": "VEDL",
    "sail": "SAIL",
    "nmdc": "NMDC",
    "coal india": "COALINDIA",
    "larsen": "LT",
    "l&t": "LT",
    "larsen and toubro": "LT",
    "larsen & toubro": "LT",
    "ultratech": "ULTRACEMCO",
    "ultratech cement": "ULTRACEMCO",
    "acc": "ACC",
    "ambuja": "AMBUJACEM",
    "shree cement": "SHREECEM",
    "grasim": "GRASIM",

    # Telecom
    "airtel": "BHARTIARTL",
    "bharti airtel": "BHARTIARTL",
    "jio": "RELIANCE",
    "vodafone": "VODAFONEIDEA",
    "vi": "VODAFONEIDEA",

    # Finance / Insurance
    "bajaj finance": "BAJFINANCE",
    "bajaj finserv": "BAJAJFINSV",
    "hdfc life": "HDFCLIFE",
    "sbi life": "SBILIFE",
    "icici prudential": "ICICIPRULI",
    "muthoot": "MUTHOOTFIN",
    "cholamandalam": "CHOLAFIN",

    # Markets / Indices
    "nifty": "NIFTY50",
    "sensex": "SENSEX",
    "nse": "NIFTY50",
    "bse": "SENSEX",

    # Others
    "adani": "ADANIENT",
    "adani enterprises": "ADANIENT",
    "adani ports": "ADANIPORTS",
    "adani green": "ADANIGREEN",
    "adani power": "ADANIPOWER",
    "titan": "TITAN",
    "asian paints": "ASIANPAINT",
    "pidilite": "PIDILITIND",
    "havells": "HAVELLS",
    "voltas": "VOLTAS",
    "siemens": "SIEMENS",
    "abb": "ABB",
    "zomato": "ZOMATO",
    "paytm": "PAYTM",
    "nykaa": "FSN",
    "policybazaar": "POLICYBZR",
    "delhivery": "DELHIVERY",
    "irctc": "IRCTC",
    "irfc": "IRFC",
    "lic": "LICI",
}


def resolve(raw: str) -> Optional[str]:
    """
    Resolve a raw company name / ticker hint to an NSE ticker.

    Parameters
    ----------
    raw : raw string from news headline — could be "Tata Consultancy",
          "TCS", "$TCS", "tcs q4 results", etc.

    Returns
    -------
    NSE ticker string (e.g. "TCS") or None if not recognized
    """
    if not raw:
        return None

    # Strip cashtag prefix
    cleaned = raw.strip().lstrip("$").lower()

    # Direct lookup
    if cleaned in TICKER_MAP:
        return TICKER_MAP[cleaned]

    # Partial match — check if any key is contained in the input
    for key, ticker in TICKER_MAP.items():
        if key in cleaned or cleaned in key:
            return ticker

    # If it's already uppercase 2-10 chars, assume it's a valid ticker
    upper = raw.strip().upper()
    if re.match(r'^[A-Z&\-]{2,10}$', upper):
        return upper

    return None


def resolve_batch(raw_list: list[str]) -> dict[str, Optional[str]]:
    """Resolve a list of raw names. Returns {raw: ticker} dict."""
    return {raw: resolve(raw) for raw in raw_list}