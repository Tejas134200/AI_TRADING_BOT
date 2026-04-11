"""
module2_ai_engine/llm_analyzer.py
-----------------------------------
Optional LLM-based analysis for ambiguous articles where
FinBERT scores fall into the uncertainty zone.

Providers supported:
  - "groq"   : Groq Cloud API (Free, fast LPU inference)
  - "ollama" : Local Llama/Mistral (Free, private)
  - "none"   : Disabled (default)
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

# Ensure GROQ_API_KEY is added to your config/settings.py
from config.settings import LLM_PROVIDER, OLLAMA_URL, GROQ_API_KEY

logger = logging.getLogger(__name__)

# Only trigger LLM when FinBERT confidence is in this uncertainty band
LLM_TRIGGER_THRESHOLD = (0.40, 0.65)


@dataclass
class LLMResult:
    ticker     : str
    sentiment  : str    # "positive" | "negative" | "neutral"
    score      : float  # 0.0–1.0
    reason     : str    # one-line explanation from LLM
    provider   : str    # "groq" | "ollama" | "none"


def should_use_llm(finbert_score: float) -> bool:
    """Check if FinBERT score warrants LLM escalation."""
    low, high = LLM_TRIGGER_THRESHOLD
    return LLM_PROVIDER != "none" and low <= finbert_score <= high


def analyze(text: str, ticker: str, finbert_score: float) -> Optional[LLMResult]:
    """Escalate to LLM when FinBERT is uncertain."""
    if not should_use_llm(finbert_score):
        return None

    logger.info(
        f"[llm] FinBERT score {finbert_score:.2f} uncertain — "
        f"escalating to {LLM_PROVIDER} for {ticker}"
    )

    if LLM_PROVIDER == "groq":
        return _analyze_groq(text, ticker)
    elif LLM_PROVIDER == "ollama":
        return _analyze_ollama(text, ticker)
    else:
        return None


# ─────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────

def _build_prompt(text: str, ticker: str) -> str:
    return f"""You are a financial analyst AI. Analyze this news article about {ticker} and respond ONLY with a JSON object.

Article:
{text[:800]}

Respond with exactly this JSON format — no other text:
{{
  "sentiment": "positive" or "negative" or "neutral",
  "score": <float between 0.0 and 1.0 where 1.0 is most positive>,
  "reason": "<one sentence explanation>"
}}"""


# ─────────────────────────────────────────────
# GROQ PROVIDER (Free & Fast Cloud AI)
# ─────────────────────────────────────────────

def _analyze_groq(text: str, ticker: str) -> Optional[LLMResult]:
    if not GROQ_API_KEY:
        logger.warning("[llm] GROQ_API_KEY not set in .env")
        return None
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        
        # Using llama-3.1-8b-instant: very fast and free
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": _build_prompt(text, ticker)}],
            response_format={"type": "json_object"}
        )
        
        raw = completion.choices[0].message.content
        data = json.loads(raw)
        
        return LLMResult(
            ticker=ticker,
            sentiment=data["sentiment"],
            score=float(data["score"]),
            reason=data.get("reason", ""),
            provider="groq",
        )
    except Exception as e:
        logger.error(f"[llm] Groq call failed: {e}")
        return None


# ─────────────────────────────────────────────
# OLLAMA PROVIDER (Local LLM)
# ─────────────────────────────────────────────

def _analyze_ollama(text: str, ticker: str) -> Optional[LLMResult]:
    try:
        import requests
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model"  : "mistral",  
                "prompt" : _build_prompt(text, ticker),
                "stream" : False,
                "format" : "json",
            },
            timeout=30,
        )
        response.raise_for_status()
        raw  = response.json().get("response", "{}")
        data = json.loads(raw)
        
        return LLMResult(
            ticker=ticker,
            sentiment=data["sentiment"],
            score=float(data["score"]),
            reason=data.get("reason", ""),
            provider="ollama",
        )
    except Exception as e:
        logger.error(f"[llm] Ollama call failed: {e}")
        return None