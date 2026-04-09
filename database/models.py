"""
database/models.py
------------------
SQLAlchemy ORM models.  One class = one MySQL table.

Tables:
  1. articles        — raw normalized news articles from Module 1
  2. scored_articles — AI analysis output from Module 2
  3. watchlist       — active candidates from Module 3
  4. signals         — technical analysis output from Module 4
  5. trades          — every order placed/simulated by Module 5
  6. positions       — current open positions tracker
  7. daily_pnl       — end-of-day summary for reporting
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, Text, Enum, ForeignKey, Index,
    create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from config.settings import DATABASE_URL

Base = declarative_base()


# ─────────────────────────────────────────────
# 1. ARTICLES  (Module 1 output)
# ─────────────────────────────────────────────

class Article(Base):
    __tablename__ = "articles"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    hash        = Column(String(64), unique=True, nullable=False)   # sha256 of title+source
    title       = Column(String(512), nullable=False)
    content     = Column(Text)
    source      = Column(String(64), nullable=False)                # "newsapi"|"google_news"|"nse_bse"|"twitter"
    url         = Column(String(1024))
    ticker_hint = Column(String(32))                                # raw company/ticker found in headline
    published_at = Column(DateTime, nullable=False)
    fetched_at  = Column(DateTime, default=datetime.utcnow)

    # relationship
    scored = relationship("ScoredArticle", back_populates="article", uselist=False)

    __table_args__ = (
        Index("ix_articles_ticker_hint", "ticker_hint"),
        Index("ix_articles_published_at", "published_at"),
    )

    def __repr__(self):
        return f"<Article id={self.id} source={self.source} ticker={self.ticker_hint}>"


# ─────────────────────────────────────────────
# 2. SCORED ARTICLES  (Module 2 output)
# ─────────────────────────────────────────────

class ScoredArticle(Base):
    __tablename__ = "scored_articles"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    article_id  = Column(Integer, ForeignKey("articles.id"), nullable=False)
    ticker      = Column(String(32), nullable=False)                # resolved NSE/BSE ticker, e.g. "TCS"
    exchange    = Column(String(8), default="NSE")

    # Sentiment output from FinBERT
    sentiment        = Column(Enum("positive", "negative", "neutral"), nullable=False)
    sentiment_score  = Column(Float, nullable=False)                # 0.0 – 1.0, positive direction

    # Keyword flags
    bullish_keywords = Column(Text)                                 # JSON array of matched keywords
    bearish_keywords = Column(Text)
    keyword_boost    = Column(Float, default=0.0)                   # +/- applied to sentiment_score

    # Final adjusted score for this article
    final_score = Column(Float, nullable=False)

    analyzed_at = Column(DateTime, default=datetime.utcnow)

    article = relationship("Article", back_populates="scored")

    __table_args__ = (
        Index("ix_scored_ticker", "ticker"),
        Index("ix_scored_analyzed_at", "analyzed_at"),
    )

    def __repr__(self):
        return (
            f"<ScoredArticle ticker={self.ticker} "
            f"sentiment={self.sentiment} score={self.final_score:.2f}>"
        )


# ─────────────────────────────────────────────
# 3. WATCHLIST  (Module 3 output)
# ─────────────────────────────────────────────

class WatchlistEntry(Base):
    __tablename__ = "watchlist"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    ticker          = Column(String(32), nullable=False)
    exchange        = Column(String(8), default="NSE")

    avg_sentiment   = Column(Float, nullable=False)    # rolling 2h avg sentiment score
    mention_count   = Column(Integer, nullable=False)  # distinct article mentions in window
    volume_spike    = Column(Boolean, default=False)   # True if vol > 1.5× 20d avg

    status          = Column(
        Enum("active", "promoted", "expired", "rejected"),
        default="active"
    )
    # "active"   = in watchlist, awaiting technical analysis
    # "promoted" = passed technical check, passed to executor
    # "expired"  = window elapsed, no signal
    # "rejected" = failed technical check

    window_start    = Column(DateTime, nullable=False)
    window_end      = Column(DateTime, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    signals = relationship("TechnicalSignal", back_populates="watchlist_entry")

    __table_args__ = (
        Index("ix_watchlist_ticker_status", "ticker", "status"),
    )

    def __repr__(self):
        return (
            f"<WatchlistEntry ticker={self.ticker} "
            f"sentiment={self.avg_sentiment:.2f} mentions={self.mention_count} "
            f"status={self.status}>"
        )


# ─────────────────────────────────────────────
# 4. TECHNICAL SIGNALS  (Module 4 output)
# ─────────────────────────────────────────────

class TechnicalSignal(Base):
    __tablename__ = "signals"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    watchlist_id     = Column(Integer, ForeignKey("watchlist.id"), nullable=False)
    ticker           = Column(String(32), nullable=False)
    exchange         = Column(String(8), default="NSE")

    # Indicator values at time of analysis
    rsi              = Column(Float)
    macd_value       = Column(Float)
    macd_signal      = Column(Float)
    macd_histogram   = Column(Float)
    ma_20            = Column(Float)
    ma_50            = Column(Float)
    ma_200           = Column(Float)
    bb_upper         = Column(Float)   # Bollinger Band upper
    bb_lower         = Column(Float)   # Bollinger Band lower
    current_price    = Column(Float)
    volume           = Column(Float)
    volume_avg_20d   = Column(Float)

    # Derived signals
    signal_direction = Column(Enum("BUY", "SELL", "HOLD"), nullable=False)
    technical_score  = Column(Float, nullable=False)   # 0.0–1.0
    composite_score  = Column(Float, nullable=False)   # 0.4×sentiment + 0.6×technical

    # Human-readable reason string, e.g. "RSI=38 MACD bullish cross price>MA50"
    reason           = Column(String(256))

    analyzed_at      = Column(DateTime, default=datetime.utcnow)

    watchlist_entry  = relationship("WatchlistEntry", back_populates="signals")
    trade            = relationship("Trade", back_populates="signal", uselist=False)

    __table_args__ = (
        Index("ix_signals_ticker", "ticker"),
        Index("ix_signals_direction", "signal_direction"),
    )

    def __repr__(self):
        return (
            f"<TechnicalSignal ticker={self.ticker} "
            f"dir={self.signal_direction} composite={self.composite_score:.2f}>"
        )


# ─────────────────────────────────────────────
# 5. TRADES  (Module 5 output)
# ─────────────────────────────────────────────

class Trade(Base):
    __tablename__ = "trades"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    signal_id       = Column(Integer, ForeignKey("signals.id"), nullable=True)

    ticker          = Column(String(32), nullable=False)
    exchange        = Column(String(8), default="NSE")
    side            = Column(Enum("BUY", "SELL"), nullable=False)
    quantity        = Column(Integer, nullable=False)
    order_type      = Column(String(16), default="MARKET")          # "MARKET" | "LIMIT"
    product_type    = Column(String(8), default="CNC")              # "CNC" | "MIS"

    # Price fields
    limit_price     = Column(Float)                                 # None for MARKET orders
    filled_price    = Column(Float)                                 # actual fill price
    stop_loss_price = Column(Float)
    take_profit_price = Column(Float)

    # Order lifecycle
    kite_order_id   = Column(String(64))                            # Zerodha order ID (None in paper mode)
    status          = Column(
        Enum("pending", "open", "complete", "cancelled", "rejected"),
        default="pending"
    )
    mode            = Column(Enum("paper", "live"), nullable=False) # always set from TRADING_MODE

    # P&L (filled in when position is closed)
    exit_price      = Column(Float)
    pnl             = Column(Float)
    pnl_pct         = Column(Float)
    exit_reason     = Column(String(32))                            # "take_profit"|"stop_loss"|"signal_exit"

    composite_score = Column(Float)                                 # copied from signal at trade time

    placed_at       = Column(DateTime, default=datetime.utcnow)
    filled_at       = Column(DateTime)
    closed_at       = Column(DateTime)

    signal          = relationship("TechnicalSignal", back_populates="trade")

    __table_args__ = (
        Index("ix_trades_ticker", "ticker"),
        Index("ix_trades_status", "status"),
        Index("ix_trades_placed_at", "placed_at"),
    )

    def __repr__(self):
        return (
            f"<Trade id={self.id} ticker={self.ticker} "
            f"side={self.side} qty={self.quantity} "
            f"status={self.status} mode={self.mode}>"
        )


# ─────────────────────────────────────────────
# 6. POSITIONS  (live tracker — module 5)
# ─────────────────────────────────────────────

class Position(Base):
    __tablename__ = "positions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    trade_id        = Column(Integer, ForeignKey("trades.id"), nullable=False)

    ticker          = Column(String(32), nullable=False, unique=True)  # one row per open position
    exchange        = Column(String(8), default="NSE")
    quantity        = Column(Integer, nullable=False)
    avg_buy_price   = Column(Float, nullable=False)
    current_price   = Column(Float)
    stop_loss_price = Column(Float)
    take_profit_price = Column(Float)

    unrealized_pnl  = Column(Float)
    unrealized_pnl_pct = Column(Float)

    opened_at       = Column(DateTime, default=datetime.utcnow)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return (
            f"<Position ticker={self.ticker} qty={self.quantity} "
            f"avg_price={self.avg_buy_price} pnl={self.unrealized_pnl}>"
        )


# ─────────────────────────────────────────────
# 7. DAILY PNL SUMMARY  (notification / reporting)
# ─────────────────────────────────────────────

class DailyPnl(Base):
    __tablename__ = "daily_pnl"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    date            = Column(DateTime, nullable=False, unique=True)

    total_trades    = Column(Integer, default=0)
    winning_trades  = Column(Integer, default=0)
    losing_trades   = Column(Integer, default=0)
    gross_pnl       = Column(Float, default=0.0)
    net_pnl         = Column(Float, default=0.0)    # after brokerage estimates
    win_rate_pct    = Column(Float)

    created_at      = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return (
            f"<DailyPnl date={self.date.date()} "
            f"net_pnl={self.net_pnl} win_rate={self.win_rate_pct}%>"
        )


# ─────────────────────────────────────────────
# DB SESSION FACTORY
# ─────────────────────────────────────────────

engine = create_engine(
    DATABASE_URL,
    pool_size=5,          # keep 5 connections open
    max_overflow=10,      # allow 10 extra under peak load
    pool_recycle=3600,    # recycle connections every hour (prevents MySQL timeout drops)
    echo=False,           # set True temporarily for SQL debug logging
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """
    Dependency-injection style session getter.
    Use as a context manager:

        with get_db() as db:
            articles = db.query(Article).filter_by(ticker_hint="TCS").all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_tables():
    """
    Create all tables if they don't exist.
    Call this once at app startup or run scripts/setup_db.sh instead.
    """
    Base.metadata.create_all(bind=engine)
    print("[database] All tables created (or already exist).")


if __name__ == "__main__":
    create_tables()