"""
config/settings.py
------------------
Single source of truth for all configuration.
Every module imports from here — never read os.environ directly elsewhere.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
# Load .env file (ignored if env vars are already set, e.g. in Docker)
load_dotenv(dotenv_path=env_path, override=True)
# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────

def _require(key: str) -> str:
    """Raise immediately at startup if a critical env var is missing."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"[settings] Required environment variable '{key}' is not set. "
            f"Check your .env file or container environment."
        )
    return val

def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ─────────────────────────────────────────────
# ZERODHA KITE CONNECT
# ─────────────────────────────────────────────

KITE_API_KEY      = _get("KITE_API_KEY")
KITE_API_SECRET   = _get("KITE_API_SECRET")
KITE_ACCESS_TOKEN = _get("KITE_ACCESS_TOKEN")   # refreshed daily via login flow
KITE_BASE_URL     = _get("KITE_BASE_URL", "https://api.kite.trade")

# Set to "paper" for simulation, "live" for real orders
TRADING_MODE = _get("TRADING_MODE", "paper")   # "paper" | "live"


# ─────────────────────────────────────────────
# NEWS SOURCES
# ─────────────────────────────────────────────

NEWSAPI_KEY         = _get("NEWSAPI_KEY")
TWITTER_BEARER_TOKEN = _get("TWITTER_BEARER_TOKEN")   # optional


# ─────────────────────────────────────────────
# DATABASE (MySQL via SQLAlchemy)
# ─────────────────────────────────────────────

DB_HOST     = _get("DB_HOST", "localhost")
DB_PORT     = _get("DB_PORT", "3306")
DB_NAME     = _get("DB_NAME", "trading_bot")
DB_USER     = _require("DB_USER")
DB_PASSWORD = _require("DB_PASSWORD")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


# ─────────────────────────────────────────────
# REDIS (dedup queue + watchlist cache)
# ─────────────────────────────────────────────

REDIS_HOST     = _get("REDIS_HOST", "localhost")
REDIS_PORT     = int(_get("REDIS_PORT", "6379"))
REDIS_PASSWORD = _get("REDIS_PASSWORD", "")
REDIS_DB       = int(_get("REDIS_DB", "0"))

# Keys
REDIS_NEWS_QUEUE_KEY    = "news:queue"          # List — pending articles for AI engine
REDIS_WATCHLIST_KEY     = "filter:watchlist"    # Sorted set — stock: composite score
REDIS_DEDUP_PREFIX      = "dedup:"              # dedup:<article_hash> → "1"
REDIS_DEDUP_TTL_SECONDS = 3600 * 4              # 4 hours dedup window


# ─────────────────────────────────────────────
# MODULE 1 — NEWS COLLECTOR
# ─────────────────────────────────────────────

NEWS_FETCH_INTERVAL_SECONDS = int(_get("NEWS_FETCH_INTERVAL_SECONDS", "300"))  # 5 min
NEWS_SOURCES = ["newsapi", "google_news", "nse_bse"]   # add "twitter" to enable


# ─────────────────────────────────────────────
# MODULE 2 — AI ANALYSIS ENGINE
# ─────────────────────────────────────────────

# FinBERT model identifier (HuggingFace hub or local path)
FINBERT_MODEL = _get("FINBERT_MODEL", "ProsusAI/finbert")
AI_BATCH_SIZE = int(_get("AI_BATCH_SIZE", "8"))         # articles per inference batch

# LLM fallback (optional — Ollama local or Claude API)
LLM_PROVIDER  = _get("LLM_PROVIDER", "none")            # "ollama" | "anthropic" | "none"
GROQ_API_KEY = _get("GROQ_API_KEY","")
OLLAMA_URL    = _get("OLLAMA_URL", "http://localhost:11434")
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY", "")

# Keywords that boost sentiment score
BULLISH_KEYWORDS = [
    "acquisition", "merger", "profit growth", "revenue beat",
    "government contract", "regulatory approval", "dividend increase",
    "buyback", "upgrade", "outperform", "expansion",
]
BEARISH_KEYWORDS = [
    "fraud", "scam", "debt downgrade", "management exit", "sebi notice",
    "probe", "loss widening", "revenue miss", "downgrade", "recall",
    "lawsuit", "penalty", "suspension",
]


# ─────────────────────────────────────────────
# MODULE 3 — STOCK FILTER
# ─────────────────────────────────────────────

FILTER_MIN_SENTIMENT_SCORE = float(_get("FILTER_MIN_SENTIMENT_SCORE", "0.70"))
FILTER_MIN_MENTION_COUNT   = int(_get("FILTER_MIN_MENTION_COUNT", "3"))
FILTER_ROLLING_WINDOW_HOURS = int(_get("FILTER_ROLLING_WINDOW_HOURS", "2"))
FILTER_VOLUME_SPIKE_MULTIPLIER = float(_get("FILTER_VOLUME_SPIKE_MULTIPLIER", "1.5"))
FILTER_MAX_WATCHLIST_SIZE   = int(_get("FILTER_MAX_WATCHLIST_SIZE", "8"))


# ─────────────────────────────────────────────
# MODULE 4 — TECHNICAL ANALYSIS
# ─────────────────────────────────────────────

# Candle interval for OHLCV data
TA_CANDLE_INTERVAL = _get("TA_CANDLE_INTERVAL", "day")   # "minute"|"5minute"|"day"
TA_LOOKBACK_DAYS   = int(_get("TA_LOOKBACK_DAYS", "200"))

# Moving averages
MA_SHORT  = int(_get("MA_SHORT", "20"))
MA_MEDIUM = int(_get("MA_MEDIUM", "50"))
MA_LONG   = int(_get("MA_LONG", "200"))

# RSI
RSI_PERIOD      = int(_get("RSI_PERIOD", "14"))
RSI_OVERSOLD    = float(_get("RSI_OVERSOLD", "40"))    # buy zone threshold
RSI_OVERBOUGHT  = float(_get("RSI_OVERBOUGHT", "70"))  # exit zone threshold

# MACD
MACD_FAST   = int(_get("MACD_FAST", "12"))
MACD_SLOW   = int(_get("MACD_SLOW", "26"))
MACD_SIGNAL = int(_get("MACD_SIGNAL", "9"))

# Score weights (must sum to 1.0)
SCORE_WEIGHT_SENTIMENT  = float(_get("SCORE_WEIGHT_SENTIMENT", "0.40"))
SCORE_WEIGHT_TECHNICAL  = float(_get("SCORE_WEIGHT_TECHNICAL", "0.60"))

# Minimum composite score to proceed to trade execution
TRADE_SIGNAL_THRESHOLD = float(_get("TRADE_SIGNAL_THRESHOLD", "0.75"))


# ─────────────────────────────────────────────
# MODULE 5 — TRADE EXECUTOR
# ─────────────────────────────────────────────

RISK_MAX_POSITIONS        = int(_get("RISK_MAX_POSITIONS", "3"))
RISK_MAX_CAPITAL_PCT      = float(_get("RISK_MAX_CAPITAL_PCT", "0.10"))  # 10% per trade
RISK_STOP_LOSS_PCT        = float(_get("RISK_STOP_LOSS_PCT", "0.02"))    # 2% stop loss
RISK_TAKE_PROFIT_PCT      = float(_get("RISK_TAKE_PROFIT_PCT", "0.05"))  # 5% take profit
TRADE_EXCHANGE            = _get("TRADE_EXCHANGE", "NSE")
TRADE_PRODUCT_TYPE        = _get("TRADE_PRODUCT_TYPE", "CNC")  # CNC=delivery, MIS=intraday


# ─────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = _get("TELEGRAM_CHAT_ID", "")
AWS_SES_FROM_EMAIL = _get("AWS_SES_FROM_EMAIL", "")
ALERT_EMAIL        = _get("ALERT_EMAIL", "")


# ─────────────────────────────────────────────
# STARTUP VALIDATION
# ─────────────────────────────────────────────

def validate():
    """
    Call once at app startup (e.g. in main.py or scheduler.py).
    Catches misconfigurations before the first trade cycle runs.
    """
    assert SCORE_WEIGHT_SENTIMENT + SCORE_WEIGHT_TECHNICAL == 1.0, (
        "SCORE_WEIGHT_SENTIMENT + SCORE_WEIGHT_TECHNICAL must equal 1.0"
    )
    assert TRADING_MODE in ("paper", "live"), (
        f"TRADING_MODE must be 'paper' or 'live', got: {TRADING_MODE}"
    )
    if TRADING_MODE == "live" and not KITE_ACCESS_TOKEN:
        raise EnvironmentError(
            "TRADING_MODE=live requires KITE_ACCESS_TOKEN to be set. "
            "Run the Kite login flow first."
        )
    print(f"[settings] Config validated. Trading mode: {TRADING_MODE.upper()}")