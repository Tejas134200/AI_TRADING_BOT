"""
module2_ai_engine/sentiment_analyzer.py
-----------------------------------------
Runs FinBERT sentiment analysis on article text.

FinBERT is a BERT model fine-tuned on financial text — it understands
phrases like "margin compression" (negative) vs "margin expansion"
(positive) that generic models score incorrectly.

Model: ProsusAI/finbert  (auto-downloaded from HuggingFace on first run)
Output: positive | negative | neutral  +  confidence score 0.0–1.0

Install:
    pip install transformers torch

The model is loaded ONCE at startup and reused for all articles.
First run downloads ~500MB to module2_ai_engine/models/ cache.
"""

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from config.settings import FINBERT_MODEL, AI_BATCH_SIZE

logger = logging.getLogger(__name__)

# Point HuggingFace cache to our local models/ directory
_MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.environ.setdefault("TRANSFORMERS_CACHE", _MODELS_DIR)

# Pipeline loaded once at module level
_pipeline = None
_pipeline_loaded = False


def _load_pipeline():
    """Load FinBERT pipeline once. Called lazily on first use."""
    global _pipeline, _pipeline_loaded
    if _pipeline_loaded:
        return

    try:
        from transformers import pipeline
        logger.info(f"[sentiment] Loading FinBERT model: {FINBERT_MODEL}")
        logger.info(f"[sentiment] Cache dir: {_MODELS_DIR}")
        logger.info("[sentiment] First run will download ~500MB — please wait...")

        _pipeline = pipeline(
            task            = "text-classification",
            model           = FINBERT_MODEL,
            tokenizer       = FINBERT_MODEL,
            top_k           = None,        # return all 3 class scores
            truncation      = True,
            max_length      = 512,
            cache_dir       = _MODELS_DIR,
        )
        _pipeline_loaded = True
        logger.info("[sentiment] FinBERT pipeline ready")

    except ImportError:
        logger.error(
            "[sentiment] transformers not installed. "
            "Run: pip install transformers torch"
        )
    except Exception as e:
        logger.error(f"[sentiment] Failed to load FinBERT: {e}")


# ─────────────────────────────────────────────
# RESULT DATACLASS
# ─────────────────────────────────────────────

@dataclass
class SentimentResult:
    label      : str    # "positive" | "negative" | "neutral"
    score      : float  # confidence of the winning label (0.0–1.0)
    positive   : float  # raw positive class probability
    negative   : float  # raw negative class probability
    neutral    : float  # raw neutral class probability

    @property
    def directional_score(self) -> float:
        """
        Single score from 0.0 (very negative) to 1.0 (very positive).
        Neutral maps to 0.5.
        Used downstream for filtering and composite scoring.
        """
        return round(self.positive - self.negative + 0.5, 4)

    def __repr__(self):
        return (
            f"<Sentiment label={self.label} score={self.score:.2f} "
            f"directional={self.directional_score:.2f}>"
        )


# ─────────────────────────────────────────────
# MAIN FUNCTIONS
# ─────────────────────────────────────────────

def analyze(text: str) -> Optional[SentimentResult]:
    """
    Run FinBERT on a single article text.

    Parameters
    ----------
    text : article.full_text (title + content, up to 512 tokens)

    Returns
    -------
    SentimentResult or None if pipeline failed to load
    """
    _load_pipeline()
    if not _pipeline:
        return _fallback_sentiment(text)

    try:
        # FinBERT returns list of [{'label': ..., 'score': ...}] per class
        results = _pipeline(text[:1500])  # truncate for speed

        # Flatten the list of dicts
        scores = {r["label"].lower(): r["score"] for r in results[0]}

        positive = scores.get("positive", 0.0)
        negative = scores.get("negative", 0.0)
        neutral  = scores.get("neutral",  0.0)

        # Winning label
        label = max(scores, key=scores.get)
        score = scores[label]

        return SentimentResult(
            label    = label,
            score    = round(score, 4),
            positive = round(positive, 4),
            negative = round(negative, 4),
            neutral  = round(neutral, 4),
        )

    except Exception as e:
        logger.error(f"[sentiment] Inference failed: {e}")
        return _fallback_sentiment(text)


def analyze_batch(texts: List[str]) -> List[Optional[SentimentResult]]:
    """
    Run FinBERT on a batch of texts (more efficient than calling analyze() in a loop).

    Parameters
    ----------
    texts : list of article.full_text strings

    Returns
    -------
    List of SentimentResult (same order as input)
    """
    _load_pipeline()
    if not _pipeline:
        return [_fallback_sentiment(t) for t in texts]

    results = []
    # Process in batches of AI_BATCH_SIZE
    for i in range(0, len(texts), AI_BATCH_SIZE):
        batch = [t[:1500] for t in texts[i:i + AI_BATCH_SIZE]]
        try:
            batch_results = _pipeline(batch)
            for item in batch_results:
                scores = {r["label"].lower(): r["score"] for r in item}
                positive = scores.get("positive", 0.0)
                negative = scores.get("negative", 0.0)
                neutral  = scores.get("neutral",  0.0)
                label    = max(scores, key=scores.get)
                results.append(SentimentResult(
                    label    = label,
                    score    = round(scores[label], 4),
                    positive = round(positive, 4),
                    negative = round(negative, 4),
                    neutral  = round(neutral, 4),
                ))
        except Exception as e:
            logger.error(f"[sentiment] Batch inference failed: {e}")
            results.extend([_fallback_sentiment(t) for t in batch])

    return results


def _fallback_sentiment(text: str) -> SentimentResult:
    """
    Simple keyword-based fallback when FinBERT is unavailable.
    Much less accurate but keeps the pipeline running.
    """
    positive_words = ["profit", "growth", "rally", "gain", "beat", "strong", "buy", "upgrade"]
    negative_words = ["loss", "fraud", "decline", "fall", "miss", "weak", "sell", "probe"]

    lower = text.lower()
    pos_count = sum(1 for w in positive_words if w in lower)
    neg_count = sum(1 for w in negative_words if w in lower)

    if pos_count > neg_count:
        return SentimentResult(label="positive", score=0.6,
                               positive=0.6, negative=0.2, neutral=0.2)
    elif neg_count > pos_count:
        return SentimentResult(label="negative", score=0.6,
                               positive=0.2, negative=0.6, neutral=0.2)
    else:
        return SentimentResult(label="neutral", score=0.5,
                               positive=0.25, negative=0.25, neutral=0.5)