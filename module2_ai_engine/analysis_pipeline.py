"""
module2_ai_engine/analysis_pipeline.py
----------------------------------------
Orchestrates all three analyzers for each article and
writes a ScoredArticle row to MySQL.

Pipeline per article:
  Article
    ├── ner_extractor     →  resolved NSE ticker
    ├── sentiment_analyzer →  FinBERT pos/neg/neutral + score
    ├── keyword_detector  →  bullish/bearish keyword boost
    ├── llm_analyzer      →  optional escalation if FinBERT uncertain
    └── final_score       =  clamp(sentiment_directional + keyword_boost, 0, 1)
    → ScoredArticle saved to MySQL

Run this directly to process all pending articles in Redis queue:
    python -m module2_ai_engine.analysis_pipeline
"""

import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers= [logging.StreamHandler(sys.stdout)],
)


# ─────────────────────────────────────────────
# SCORED ARTICLE DATACLASS
# ─────────────────────────────────────────────

@dataclass
class ScoredArticle:
    """
    Output of the AI analysis pipeline for one article.
    This is what Module 3 (stock filter) reads.
    """
    article_hash     : str
    ticker           : str
    exchange         : str
    sentiment        : str    # "positive" | "negative" | "neutral"
    sentiment_score  : float  # FinBERT directional score (0–1)
    bullish_keywords : List[str]
    bearish_keywords : List[str]
    keyword_boost    : float  # net boost from keywords
    final_score      : float  # sentiment_score + keyword_boost, clamped 0–1
    analyzed_at      : datetime
    reason           : str    # human-readable summary of why

    def __repr__(self):
        return (
            f"<ScoredArticle ticker={self.ticker} "
            f"sentiment={self.sentiment} "
            f"final_score={self.final_score:.2f} "
            f"keywords={len(self.bullish_keywords)}B/{len(self.bearish_keywords)}N>"
        )


# ─────────────────────────────────────────────
# SINGLE ARTICLE ANALYSIS
# ─────────────────────────────────────────────

def analyze_article(article_dict: dict) -> Optional[ScoredArticle]:
    """
    Run the full AI pipeline on one article dict.

    Parameters
    ----------
    article_dict : Article.to_dict() output from Redis queue

    Returns
    -------
    ScoredArticle or None if ticker could not be resolved
    """
    from module1_news_collector.normalizer import Article
    from module2_ai_engine.ner_extractor import extract_ticker
    from module2_ai_engine.sentiment_analyzer import analyze as sentiment_analyze
    from module2_ai_engine.keyword_detector import detect as keyword_detect
    from module2_ai_engine.llm_analyzer import analyze as llm_analyze

    article = Article.from_dict(article_dict)

    # ── Step 1: Resolve ticker ────────────────
    ticker = extract_ticker(article.full_text, article.ticker_hint)
    if not ticker:
        logger.debug(f"[pipeline] No ticker resolved — skipping: {article.title[:50]}")
        return None

    # ── Step 2: FinBERT sentiment ─────────────
    sentiment = sentiment_analyze(article.full_text)
    if not sentiment:
        logger.warning(f"[pipeline] Sentiment failed for {ticker} — skipping")
        return None

    # ── Step 3: Keyword detection ─────────────
    keywords = keyword_detect(article.full_text)

    # ── Step 4: LLM escalation (optional) ────
    llm_result = llm_analyze(
        text          = article.full_text,
        ticker        = ticker,
        finbert_score = sentiment.directional_score,
    )

    # Use LLM score if available, else use FinBERT
    base_score = llm_result.score if llm_result else sentiment.directional_score

    # ── Step 5: Calculate final score ─────────
    raw_final  = base_score + keywords.boost
    final_score = round(max(0.0, min(1.0, raw_final)), 4)  # clamp 0–1

    # ── Step 6: Build reason string ───────────
    reason_parts = [f"FinBERT={sentiment.label}({sentiment.score:.2f})"]
    if keywords.bullish_matches:
        reason_parts.append(f"bullish_kw={keywords.bullish_matches[:3]}")
    if keywords.bearish_matches:
        reason_parts.append(f"bearish_kw={keywords.bearish_matches[:2]}")
    if llm_result:
        reason_parts.append(f"LLM={llm_result.sentiment}({llm_result.provider})")
    reason = " | ".join(reason_parts)

    scored = ScoredArticle(
        article_hash     = article.hash,
        ticker           = ticker,
        exchange         = "NSE",
        sentiment        = sentiment.label,
        sentiment_score  = sentiment.directional_score,
        bullish_keywords = keywords.bullish_matches,
        bearish_keywords = keywords.bearish_matches,
        keyword_boost    = keywords.boost,
        final_score      = final_score,
        analyzed_at      = datetime.utcnow(),
        reason           = reason,
    )

    logger.info(
        f"[pipeline] {ticker:<12} | {sentiment.label:<8} | "
        f"score={final_score:.2f} | {reason[:80]}"
    )
    return scored


# ─────────────────────────────────────────────
# SAVE TO MYSQL
# ─────────────────────────────────────────────

def save_scored_article(scored: ScoredArticle, article_id: int):
    """Write ScoredArticle to MySQL scored_articles table."""
    try:
        from database.models import ScoredArticle as ScoredModel
        from database.connection import get_db

        with get_db() as db:
            row = ScoredModel(
                article_id       = article_id,
                ticker           = scored.ticker,
                exchange         = scored.exchange,
                sentiment        = scored.sentiment,
                sentiment_score  = scored.sentiment_score,
                bullish_keywords = json.dumps(scored.bullish_keywords),
                bearish_keywords = json.dumps(scored.bearish_keywords),
                keyword_boost    = scored.keyword_boost,
                final_score      = scored.final_score,
                analyzed_at      = scored.analyzed_at,
            )
            db.add(row)
        logger.debug(f"[pipeline] Saved scored_article for {scored.ticker}")
    except Exception as e:
        logger.error(f"[pipeline] DB save failed: {e}")


# ─────────────────────────────────────────────
# PROCESS REDIS QUEUE
# ─────────────────────────────────────────────

def process_queue():
    """
    Read all pending articles from Redis news:queue,
    run the full AI pipeline on each, save results to MySQL.

    This is what Module 3 waits for before filtering.
    """
    from config.settings import (
        REDIS_HOST, REDIS_PORT, REDIS_PASSWORD,
        REDIS_DB, REDIS_NEWS_QUEUE_KEY
    )
    from database.models import Article as ArticleModel
    from database.connection import get_db
    from module2_ai_engine.llm_analyzer import reset_call_counter

    # Reset LLM call counter for this pipeline run
    reset_call_counter()

    # Connect to Redis
    try:
        import redis as redis_lib
        r = redis_lib.Redis(
            host=REDIS_HOST, port=REDIS_PORT,
            password=REDIS_PASSWORD or None,
            db=REDIS_DB, decode_responses=True,
        )
        queue_len = r.llen(REDIS_NEWS_QUEUE_KEY)
        logger.info(f"[pipeline] {queue_len} articles in Redis queue")
    except Exception as e:
        logger.error(f"[pipeline] Redis connection failed: {e}")
        return []

    results = []
    processed = 0
    skipped   = 0

    while True:
        # Pop one article from the left of the queue (FIFO)
        item = r.lpop(REDIS_NEWS_QUEUE_KEY)
        if not item:
            break   # queue empty

        try:
            article_dict = json.loads(item)
        except json.JSONDecodeError:
            skipped += 1
            continue

        # Look up the article's DB id (needed for FK in scored_articles)
        article_id = None
        try:
            with get_db() as db:
                row = db.query(ArticleModel).filter_by(
                    hash=article_dict.get("hash")
                ).first()
                article_id = row.id if row else None
        except Exception:
            pass

        # Run full AI pipeline
        scored = analyze_article(article_dict)

        if scored and article_id:
            save_scored_article(scored, article_id)
            results.append(scored)
            processed += 1
        else:
            skipped += 1

    logger.info(
        f"[pipeline] Queue done — "
        f"processed: {processed}, skipped: {skipped}"
    )
    return results


# ─────────────────────────────────────────────
# MAIN — run directly to process queue once
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("[pipeline] Starting Module 2 — AI Analysis Engine")
    scored_articles = process_queue()

    print(f"\n{'='*60}")
    print(f"  Module 2 complete — {len(scored_articles)} articles scored")
    print(f"{'='*60}")

    # Print top results sorted by final_score
    sorted_results = sorted(scored_articles, key=lambda x: x.final_score, reverse=True)
    print(f"\n  {'TICKER':<12} {'SENTIMENT':<10} {'SCORE':<8} REASON")
    print(f"  {'-'*12} {'-'*10} {'-'*8} {'-'*30}")
    for s in sorted_results[:20]:
        print(f"  {s.ticker:<12} {s.sentiment:<10} {s.final_score:<8.2f} {s.reason[:50]}")

    print(f"\n  Full results saved to MySQL scored_articles table")
    print(f"{'='*60}\n")