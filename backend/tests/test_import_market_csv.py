from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.market_data import MarketData
from app.scripts.import_market_csv import import_market_csv, parse_market_csv, parse_market_row

TEST_SYMBOL = "TST"


def write_csv(path: Path, rows: list[str]) -> Path:
    path.write_text(
        "date,open,high,low,close,volume,adjusted_close,change_percent,avg_vol_20d\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    return path


def test_csv_row_maps_required_fields_and_ignores_extra_columns() -> None:
    row = parse_market_row(
        {
            "date": "2024-01-02",
            "open": "100.10",
            "high": "105.20",
            "low": "99.80",
            "close": "104.00",
            "volume": "1234567",
            "adjusted_close": "103.50",
            "change_percent": "4.2",
            "avg_vol_20d": "1000000",
        }
    )

    assert row.timestamp == datetime(2024, 1, 2, tzinfo=UTC)
    assert row.open_price == Decimal("100.10")
    assert row.high_price == Decimal("105.20")
    assert row.low_price == Decimal("99.80")
    assert row.close_price == Decimal("104.00")
    assert row.volume == 1234567
    assert row.adjusted_close == Decimal("103.50")


def test_parse_market_csv_reports_malformed_rows_and_uses_utc(tmp_path: Path) -> None:
    file_path = write_csv(
        tmp_path / "market.csv",
        [
            "2024-01-02,100,105,99,104,123,103,,",
            "2024-01-03,100,99,98,101,123,100,,",
            "bad-date,100,105,99,104,123,103,,",
        ],
    )

    rows, summary = parse_market_csv(file_path)

    assert [row.timestamp for row in rows] == [datetime(2024, 1, 2, tzinfo=UTC)]
    assert summary.total_csv_rows == 3
    assert summary.skipped_count == 2
    assert "high must be" in summary.skipped_rows[0].reason
    assert "ISO format" in summary.skipped_rows[1].reason


@pytest.fixture
def market_data_session() -> Generator[Session]:
    with SessionLocal() as session:
        session.execute(delete(MarketData).where(MarketData.symbol == TEST_SYMBOL))
        session.commit()
        try:
            yield session
        finally:
            session.execute(delete(MarketData).where(MarketData.symbol == TEST_SYMBOL))
            session.commit()


def test_import_upserts_existing_market_data_row(
    tmp_path: Path, market_data_session: Session
) -> None:
    initial_file = write_csv(
        tmp_path / "initial.csv",
        ["2024-01-02,100,105,99,104,123,103,,"],
    )
    updated_file = write_csv(
        tmp_path / "updated.csv",
        ["2024-01-02,100,106,99,105,456,104,,"],
    )

    initial_summary = import_market_csv(
        initial_file, symbol=TEST_SYMBOL, session=market_data_session
    )
    updated_summary = import_market_csv(
        updated_file, symbol=TEST_SYMBOL, session=market_data_session
    )
    rows = list(
        market_data_session.scalars(select(MarketData).where(MarketData.symbol == TEST_SYMBOL))
    )

    assert initial_summary.inserted_rows == 1
    assert initial_summary.updated_rows == 0
    assert updated_summary.inserted_rows == 0
    assert updated_summary.updated_rows == 1
    assert len(rows) == 1
    assert rows[0].close_price == Decimal("105")
    assert rows[0].volume == 456
