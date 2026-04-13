"""
module2_ai_engine/llm_analyzer.py
-----------------------------------
Optional LLM-based analysis for ambiguous articles where
FinBERT is genuinely uncertain (score very close to 0.50).

Threshold narrowed to (0.48, 0.52) — only fires when FinBERT
is basically coin-flip uncertain. Cuts LLM calls by ~90%.

Hard cap: MAX_LLM_CALLS_PER_RUN = 10 per pipeline run.
This prevents runaway API costs on large queues (300+ articles).

Providers supported:
  - "groq"      : Groq API (fast + cheap, recommended)
  - "anthropic" : Claude API
  - "ollama"    : local Llama / Mistral (free, private)
  - "none"      : disabled (default — FinBERT only)

Configure in .env:
    LLM_PROVIDER=groq
    GROQ_API_KEY=your_key
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from config.settings import LLM_PROVIDER, OLLAMA_URL, ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# THRESHOLDS & CAPS
# ─────────────────────────────────────────────

# Only escalate when FinBERT directional score is in this tight band
# 0.48–0.52 = genuinely uncertain (close to neutral 0.50)
LLM_TRIGGER_LOW  = 0.48
LLM_TRIGGER_HIGH = 0.52

# Hard cap per pipeline run — prevents cost blowout on large queues
MAX_LLM_CALLS_PER_RUN = 10

# Runtime counter — resets each time the module is reimported (i.e. each run)
_llm_calls_this_run = 0


@dataclass
class LLMResult:
    ticker    : str
    sentiment : str    # "positive" | "negative" | "neutral"
    score     : float  # 0.0–1.0
    reason    : str    # one-line explanation from LLM
    provider  : str    # "groq" | "anthropic" | "ollama"


# ─────────────────────────────────────────────
# GATE CHECK
# ─────────────────────────────────────────────

def should_use_llm(finbert_score: float) -> bool:
    """
    Return True only when:
      1. LLM provider is configured
      2. FinBERT score is in the tight uncertainty band (0.48–0.52)
      3. We haven't hit the per-run cap yet
    """
    global _llm_calls_this_run

    if LLM_PROVIDER == "none":
        return False

    if _llm_calls_this_run >= MAX_LLM_CALLS_PER_RUN:
        logger.debug(
            f"[llm] Cap reached ({MAX_LLM_CALLS_PER_RUN} calls) — "
            "skipping LLM for remaining articles"
        )
        return False

    return LLM_TRIGGER_LOW <= finbert_score <= LLM_TRIGGER_HIGH


def analyze(text: str, ticker: str, finbert_score: float) -> Optional[LLMResult]:
    """
    Escalate to LLM only when FinBERT is genuinely uncertain.

    Parameters
    ----------
    text          : article full_text
    ticker        : resolved NSE ticker (e.g. "TCS")
    finbert_score : FinBERT directional score

    Returns
    -------
    LLMResult or None if not triggered / provider unavailable
    """
    global _llm_calls_this_run

    if not should_use_llm(finbert_score):
        return None

    logger.info(
        f"[llm] Escalating {ticker} to {LLM_PROVIDER} "
        f"(FinBERT score={finbert_score:.3f} in uncertainty band) "
        f"[call {_llm_calls_this_run + 1}/{MAX_LLM_CALLS_PER_RUN}]"
    )

    result = None
    if LLM_PROVIDER == "groq":
        result = _analyze_groq(text, ticker)
    elif LLM_PROVIDER == "anthropic":
        result = _analyze_anthropic(text, ticker)
    elif LLM_PROVIDER == "ollama":
        result = _analyze_ollama(text, ticker)

    if result:
        _llm_calls_this_run += 1

    return result


def reset_call_counter():
    """Call this at the start of each pipeline run to reset the cap."""
    global _llm_calls_this_run
    _llm_calls_this_run = 0
    logger.debug("[llm] Call counter reset for new pipeline run")


# ─────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────

def _build_prompt(text: str, ticker: str) -> str:
    return f"""You are a financial analyst. Analyze this news about {ticker} listed on NSE India.
Respond ONLY with a JSON object, no other text.

Article:
{text[:600]}

JSON format:
{{
  "sentiment": "positive" or "negative" or "neutral",
  "score": <float 0.0 to 1.0, where 1.0 = most positive>,
  "reason": "<one sentence max>"
}}"""


# ─────────────────────────────────────────────
# GROQ PROVIDER (fast + cheap, recommended)
# ─────────────────────────────────────────────

def _analyze_groq(text: str, ticker: str) -> Optional[LLMResult]:
    try:
        from groq import Groq
        from config.settings import _get
        groq_key = _get("GROQ_API_KEY", "")
        if not groq_key:
            logger.warning("[llm] GROQ_API_KEY not set")
            return None

        client = Groq(api_key=groq_key)
        response = client.chat.completions.create(
            model    = "llama-3.3-70b-versatile",   # fast + free tier available
            messages = [{"role": "user", "content": _build_prompt(text, ticker)}],
            max_tokens      = 150,
            temperature     = 0.1,          # low temp = consistent outputs
            response_format = {"type": "json_object"},
        )
        raw  = response.choices[0].message.content.strip()
        data = json.loads(raw)
        return LLMResult(
            ticker    = ticker,
            sentiment = data["sentiment"],
            score     = float(data["score"]),
            reason    = data.get("reason", ""),
            provider  = "groq",
        )
    except Exception as e:
        logger.error(f"[llm] Groq call failed for {ticker}: {e}")
        return None


# ─────────────────────────────────────────────
# ANTHROPIC PROVIDER
# ─────────────────────────────────────────────

def _analyze_anthropic(text: str, ticker: str) -> Optional[LLMResult]:
    if not ANTHROPIC_API_KEY:
        logger.warning("[llm] ANTHROPIC_API_KEY not set")
        return None
    try:
        import anthropic
        client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model    = "claude-haiku-4-5-20251001",
            max_tokens = 150,
            messages = [{"role": "user", "content": _build_prompt(text, ticker)}],
        )
        raw  = message.content[0].text.strip()
        data = json.loads(raw)
        return LLMResult(
            ticker    = ticker,
            sentiment = data["sentiment"],
            score     = float(data["score"]),
            reason    = data.get("reason", ""),
            provider  = "anthropic",
        )
    except Exception as e:
        logger.error(f"[llm] Anthropic call failed for {ticker}: {e}")
        return None


# ─────────────────────────────────────────────
# OLLAMA PROVIDER (local)
# ─────────────────────────────────────────────

def _analyze_ollama(text: str, ticker: str) -> Optional[LLMResult]:
    try:
        import requests
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model" : "mistral",
                "prompt": _build_prompt(text, ticker),
                "stream": False,
                "format": "json",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = json.loads(response.json().get("response", "{}"))
        return LLMResult(
            ticker    = ticker,
            sentiment = data["sentiment"],
            score     = float(data["score"]),
            reason    = data.get("reason", ""),
            provider  = "ollama",
        )
    except Exception as e:
        logger.error(f"[llm] Ollama call failed for {ticker}: {e}")
        return None