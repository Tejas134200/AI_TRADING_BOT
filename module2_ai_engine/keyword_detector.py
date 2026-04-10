"""
module2_ai_engine/keyword_detector.py
---------------------------------------
Scans article text for bullish / bearish signal keywords
and returns a score boost/penalty to apply on top of FinBERT.

Why needed?
-----------
FinBERT is good at general sentiment but can miss domain-specific
finance events. "Company announces buyback" might score only 0.6
on FinBERT — but a buyback is almost always strongly bullish.
This detector catches those high-signal events explicitly.

Score impact:
  Each bullish keyword match  →  +0.05  (capped at +0.20)
  Each bearish keyword match  →  -0.07  (capped at -0.30)
"""

import re
from dataclasses import dataclass, field
from typing import List

from config.settings import BULLISH_KEYWORDS, BEARISH_KEYWORDS


# ─────────────────────────────────────────────
# EXTENDED KEYWORD LISTS (merge with settings.py)
# ─────────────────────────────────────────────

_BULLISH_EXTENDED = [
    # Earnings / Growth
    "profit growth", "revenue growth", "earnings beat", "revenue beat",
    "record profit", "record revenue", "strong results", "beats estimates",
    "above expectations", "margin expansion", "ebitda growth",
    "net profit up", "net profit rises", "pat up", "pat rises",

    # Corporate actions
    "acquisition", "merger", "takeover", "buyback", "share buyback",
    "dividend", "bonus shares", "stock split", "rights issue",
    "strategic partnership", "joint venture",

    # Contracts / Orders
    "government contract", "wins order", "order win", "order book",
    "large order", "new contract", "landmark deal",

    # Regulatory / Upgrades
    "regulatory approval", "fda approval", "sebi approval",
    "upgrade", "outperform", "buy rating", "target raised",
    "price target increased",

    # Expansion
    "expansion", "new plant", "capacity addition", "new launch",
    "market share gain", "enters new market",
]

_BEARISH_EXTENDED = [
    # Fraud / Legal
    "fraud", "scam", "corruption", "bribery", "money laundering",
    "criminal charges", "arrested", "raid", "seized",
    "sebi notice", "sebi probe", "sebi order", "penalty",
    "lawsuit", "legal action", "court order", "fir filed",

    # Management
    "ceo resignation", "md resignation", "cfo resignation",
    "management exit", "key executive leaves", "promoter selling",
    "promoter pledge",

    # Financial distress
    "debt downgrade", "credit downgrade", "rating downgrade",
    "loss widening", "revenue miss", "below expectations",
    "profit warning", "guidance cut", "write-off", "impairment",
    "npa", "bad loans", "default",

    # Operational
    "plant shutdown", "production halt", "factory fire",
    "product recall", "supply chain disruption",
    "strike", "labour unrest",

    # Regulatory / Market
    "suspension", "trading halt", "delisting",
    "downgrade", "sell rating", "target cut", "price target reduced",
    "overvalued",
]

# Merge settings.py keywords with extended lists (deduplicated)
ALL_BULLISH = list(set(BULLISH_KEYWORDS + _BULLISH_EXTENDED))
ALL_BEARISH = list(set(BEARISH_KEYWORDS + _BEARISH_EXTENDED))

# Score impact per keyword hit
BULLISH_BOOST_PER_HIT = 0.05
BEARISH_PENALTY_PER_HIT = 0.07
MAX_BULLISH_BOOST = 0.20
MAX_BEARISH_PENALTY = 0.30


# ─────────────────────────────────────────────
# RESULT DATACLASS
# ─────────────────────────────────────────────

@dataclass
class KeywordResult:
    bullish_matches : List[str] = field(default_factory=list)
    bearish_matches : List[str] = field(default_factory=list)
    boost           : float = 0.0    # net score adjustment (-0.30 to +0.20)

    @property
    def summary(self) -> str:
        parts = []
        if self.bullish_matches:
            parts.append(f"bullish: {self.bullish_matches}")
        if self.bearish_matches:
            parts.append(f"bearish: {self.bearish_matches}")
        return " | ".join(parts) if parts else "no keywords"


# ─────────────────────────────────────────────
# DETECTOR
# ─────────────────────────────────────────────

def detect(text: str) -> KeywordResult:
    """
    Scan article text for bullish/bearish keywords.

    Parameters
    ----------
    text : article title + content (use article.full_text)

    Returns
    -------
    KeywordResult with matched keywords and net score boost
    """
    if not text:
        return KeywordResult()

    lower = text.lower()
    result = KeywordResult()

    # Bullish scan
    for kw in ALL_BULLISH:
        if re.search(r'\b' + re.escape(kw) + r'\b', lower):
            result.bullish_matches.append(kw)

    # Bearish scan
    for kw in ALL_BEARISH:
        if re.search(r'\b' + re.escape(kw) + r'\b', lower):
            result.bearish_matches.append(kw)

    # Calculate net boost (capped)
    bullish_boost   = min(len(result.bullish_matches) * BULLISH_BOOST_PER_HIT, MAX_BULLISH_BOOST)
    bearish_penalty = min(len(result.bearish_matches) * BEARISH_PENALTY_PER_HIT, MAX_BEARISH_PENALTY)
    result.boost = round(bullish_boost - bearish_penalty, 4)

    return result