from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backtesting.models import MarketBar
from app.models.market_data import MarketData


def load_market_bars(session: Session, *, symbol: str, interval: str) -> list[MarketBar]:
    """Load daily bars in deterministic timestamp order."""

    rows = session.scalars(
        select(MarketData)
        .where(
            MarketData.symbol == symbol,
            MarketData.interval == interval,
        )
        .order_by(MarketData.timestamp.asc())
    )
    return [
        MarketBar(
            timestamp=row.timestamp,
            open_price=row.open_price,
            high_price=row.high_price,
            low_price=row.low_price,
            close_price=row.close_price,
            volume=row.volume,
        )
        for row in rows
    ]
