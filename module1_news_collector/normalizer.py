"""
module1_news_collector/normalizer.py
-------------------------------------
Defines the Article dataclass — the single shared data contract
between Module 1 (collection) and Module 2 (AI analysis).

Every fetcher (NewsAPI, Google News, NSE/BSE, Twitter) returns
a list of Article objects. Nothing downstream cares which source
produced it — they all speak the same shape.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────
# CORE DATACLASS
# ─────────────────────────────────────────────

@dataclass
class Article:
    """
    Normalized news article. All fetchers produce this shape.

    Fields
    ------
    title        : Headline text (required)
    content      : Full body text — can be empty string if not available
    source       : Which fetcher produced this — "newsapi" | "google_news" | "nse_bse" | "twitter"
    url          : Original article URL
    published_at : When the article was published (UTC datetime)
    ticker_hint  : Raw company name or ticker found in the headline (pre-NER, may be messy)
    fetched_at   : When our system pulled this article (set automatically)
    hash         : SHA-256 of title+source — used for Redis/DB deduplication (set automatically)
    """

    title        : str
    content      : str
    source       : str                          # "newsapi" | "google_news" | "nse_bse" | "twitter"
    url          : str
    published_at : datetime
    ticker_hint  : Optional[str] = None        # e.g. "Tata Consultancy" or "TCS" — resolved later
    fetched_at   : datetime      = field(default_factory=datetime.utcnow)
    hash         : str           = field(init=False)   # computed in __post_init__

    def __post_init__(self):
        # Compute dedup hash from title + source
        # (same article from two sources = two distinct rows, intentionally)
        raw = f"{self.title.strip().lower()}|{self.source}"
        self.hash = hashlib.sha256(raw.encode()).hexdigest()

        # Sanitize whitespace in content
        self.content = re.sub(r"\s+", " ", self.content).strip()
        self.title   = self.title.strip()

    @property
    def full_text(self) -> str:
        """Title + content combined — what the AI engine receives for analysis."""
        return f"{self.title}. {self.content}".strip()

    @property
    def age_minutes(self) -> float:
        """How many minutes ago this article was published."""
        delta = datetime.utcnow() - self.published_at
        return delta.total_seconds() / 60

    def is_fresh(self, max_age_minutes: int = 120) -> bool:
        """True if article is within the rolling analysis window (default 2 hours)."""
        return self.age_minutes <= max_age_minutes

    def to_dict(self) -> dict:
        """Serialize to dict for Redis queue (JSON-serializable)."""
        return {
            "hash"        : self.hash,
            "title"       : self.title,
            "content"     : self.content,
            "source"      : self.source,
            "url"         : self.url,
            "published_at": self.published_at.isoformat(),
            "ticker_hint" : self.ticker_hint,
            "fetched_at"  : self.fetched_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Article":
        """Deserialize from Redis queue dict back to Article."""
        return cls(
            title        = data["title"],
            content      = data["content"],
            source       = data["source"],
            url          = data["url"],
            published_at = datetime.fromisoformat(data["published_at"]),
            ticker_hint  = data.get("ticker_hint"),
            fetched_at   = datetime.fromisoformat(data["fetched_at"]),
        )

    def __repr__(self):
        age = f"{self.age_minutes:.0f}m ago"
        return (
            f"<Article source={self.source} ticker={self.ticker_hint} "
            f"published={age} hash={self.hash[:8]}...>"
        )