"""
module2_ai_engine/ner_extractor.py
------------------------------------
Extracts company names from article text using spaCy NER,
then resolves them to NSE tickers via ticker_mapper.

Why spaCy over simple regex?
-----------------------------
Regex catches "TCS" but misses "Tata Consultancy posted strong Q4".
spaCy's NER finds ORG entities like "Tata Consultancy Services",
"HDFC Bank", "Infosys" — even when not written as a ticker.

Falls back gracefully to ticker_mapper if spaCy isn't installed.

Install:
    pip install spacy
    python -m spacy download en_core_web_sm
"""

import logging
from typing import List, Optional

from module2_ai_engine.ticker_mapper import resolve

logger = logging.getLogger(__name__)

# Try loading spaCy once at import time
_nlp = None
_spacy_available = False

try:
    import spacy
    _nlp = spacy.load("en_core_web_sm")
    _spacy_available = True
    logger.info("[ner] spaCy loaded — en_core_web_sm")
except OSError:
    logger.warning(
        "[ner] spaCy model 'en_core_web_sm' not found. "
        "Run: python -m spacy download en_core_web_sm. "
        "Falling back to regex-based extraction."
    )
except ImportError:
    logger.warning(
        "[ner] spaCy not installed. Run: pip install spacy. "
        "Falling back to regex-based extraction."
    )


def extract_ticker(text: str, ticker_hint: Optional[str] = None) -> Optional[str]:
    """
    Extract the most likely NSE ticker from article text.

    Strategy:
      1. Try spaCy NER → extract ORG entities → resolve via ticker_mapper
      2. Fall back to ticker_hint from the fetcher (rough regex)
      3. Fall back to uppercase word scan

    Parameters
    ----------
    text        : article full_text (title + content)
    ticker_hint : rough hint from fetcher (may be empty or wrong)

    Returns
    -------
    NSE ticker string or None
    """

    # ── Strategy 1: spaCy NER ─────────────────
    if _spacy_available and _nlp and text:
        doc = _nlp(text[:1000])   # limit to first 1000 chars for speed
        org_entities = [ent.text for ent in doc.ents if ent.label_ == "ORG"]

        for org in org_entities:
            ticker = resolve(org)
            if ticker:
                logger.debug(f"[ner] spaCy resolved '{org}' → {ticker}")
                return ticker

    # ── Strategy 2: ticker_hint from fetcher ──
    if ticker_hint:
        ticker = resolve(ticker_hint)
        if ticker:
            logger.debug(f"[ner] hint resolved '{ticker_hint}' → {ticker}")
            return ticker

    # ── Strategy 3: scan for uppercase tickers ─
    if text:
        ticker = _scan_uppercase(text)
        if ticker:
            logger.debug(f"[ner] uppercase scan found: {ticker}")
            return ticker

    return None


def extract_all_tickers(text: str) -> List[str]:
    """
    Extract ALL company tickers mentioned in text.
    Useful for articles covering multiple companies (e.g. "TCS and Infosys both rally").

    Returns list of unique NSE tickers found.
    """
    tickers = []

    if _spacy_available and _nlp and text:
        doc = _nlp(text[:2000])
        for ent in doc.ents:
            if ent.label_ == "ORG":
                ticker = resolve(ent.text)
                if ticker and ticker not in tickers:
                    tickers.append(ticker)

    return tickers


def _scan_uppercase(text: str) -> Optional[str]:
    """
    Scan text for uppercase sequences that look like NSE tickers.
    Simple fallback when NER and hints both fail.
    """
    import re
    # Match 2-10 uppercase letters, possibly with & or -
    candidates = re.findall(r'\b[A-Z][A-Z&\-]{1,9}\b', text)
    # Skip common non-ticker uppercase words
    skip = {
        "NSE", "BSE", "RBI", "SEBI", "IPO", "FII", "FPI", "GDP",
        "CEO", "CFO", "CTO", "MD", "AGM", "EGM", "QIP", "OFS",
        "Q1", "Q2", "Q3", "Q4", "FY", "YOY", "QOQ", "PAT", "EBITDA",
        "IT", "AI", "ML", "US", "UK", "EU", "IN", "INR", "USD",
    }
    for candidate in candidates:
        if candidate not in skip:
            resolved = resolve(candidate)
            if resolved:
                return resolved
    return None