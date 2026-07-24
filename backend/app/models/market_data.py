from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    FetchedValue,
    Index,
    Numeric,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketData(Base):
    """A daily OHLCV market bar managed by the Supabase SQL migration."""

    __tablename__ = "market_data"
    __table_args__ = (
        CheckConstraint(
            "char_length(symbol) between 1 and 20 and symbol = upper(symbol)",
            name="market_data_symbol_check",
        ),
        CheckConstraint("\"interval\" in ('1d')", name="market_data_interval_check"),
        CheckConstraint(
            "open_price > 0 and high_price > 0 and low_price > 0 and close_price > 0 "
            "and (adjusted_close is null or adjusted_close > 0)",
            name="market_data_prices_positive_check",
        ),
        CheckConstraint(
            "low_price <= open_price and open_price <= high_price "
            "and low_price <= close_price and close_price <= high_price",
            name="market_data_price_range_check",
        ),
        CheckConstraint("volume >= 0", name="market_data_volume_check"),
        Index("market_data_symbol_timestamp_idx", "symbol", "timestamp"),
        {"schema": "public"},
    )

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    interval: Mapped[str] = mapped_column("interval", Text, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    high_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    low_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=FetchedValue(),
    )
