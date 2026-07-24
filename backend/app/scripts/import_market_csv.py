"""Import daily OHLCV CSV data into the Supabase-managed market_data table."""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.market_data import MarketData

REQUIRED_COLUMNS = {
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjusted_close",
}
DEFAULT_BATCH_SIZE = 500
MAX_REPORTED_SKIPPED_ROWS = 20


@dataclass(frozen=True)
class MarketDataRow:
    """A validated CSV row ready for database insertion."""

    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    adjusted_close: Decimal | None

    def as_database_values(self, *, symbol: str, interval: str) -> dict[str, object]:
        return {
            "symbol": symbol,
            "interval": interval,
            "timestamp": self.timestamp,
            "open_price": self.open_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "close_price": self.close_price,
            "volume": self.volume,
            "adjusted_close": self.adjusted_close,
        }


@dataclass(frozen=True)
class SkippedRow:
    row_number: int
    reason: str


def empty_skipped_rows() -> list[SkippedRow]:
    return []


@dataclass
class ImportSummary:
    total_csv_rows: int = 0
    inserted_rows: int = 0
    updated_rows: int = 0
    skipped_rows: list[SkippedRow] = field(default_factory=empty_skipped_rows)
    earliest_stored_timestamp: datetime | None = None
    latest_stored_timestamp: datetime | None = None
    total_symbol_rows: int = 0

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_rows)


def parse_market_csv(path: Path) -> tuple[list[MarketDataRow], ImportSummary]:
    """Parse, validate, and normalize a daily OHLCV CSV file.

    Invalid source rows are retained as skipped-row diagnostics rather than
    stopping a potentially large import. Database errors still roll back the
    entire valid-row batch transaction.
    """

    summary = ImportSummary()
    rows: list[MarketDataRow] = []
    seen_timestamps: set[datetime] = set()

    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        headers = set(reader.fieldnames or [])
        missing_columns = REQUIRED_COLUMNS - headers
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"CSV is missing required columns: {missing}.")

        for row_number, raw_row in enumerate(reader, start=2):
            summary.total_csv_rows += 1
            try:
                row = parse_market_row(raw_row)
                if row.timestamp in seen_timestamps:
                    raise ValueError("duplicate timestamp in CSV")
            except ValueError as error:
                summary.skipped_rows.append(SkippedRow(row_number, str(error)))
                continue

            seen_timestamps.add(row.timestamp)
            rows.append(row)

    return rows, summary


def parse_market_row(raw_row: dict[str, str | None]) -> MarketDataRow:
    """Map one source row to a validated UTC daily bar."""

    timestamp = datetime.combine(parse_date(raw_row.get("date")), datetime.min.time(), UTC)
    open_price = parse_positive_decimal(raw_row.get("open"), "open")
    high_price = parse_positive_decimal(raw_row.get("high"), "high")
    low_price = parse_positive_decimal(raw_row.get("low"), "low")
    close_price = parse_positive_decimal(raw_row.get("close"), "close")
    adjusted_close = parse_optional_positive_decimal(
        raw_row.get("adjusted_close"), "adjusted_close"
    )
    volume = parse_nonnegative_integer(raw_row.get("volume"), "volume")

    if high_price < open_price or high_price < low_price or high_price < close_price:
        raise ValueError("high must be greater than or equal to open, low, and close")
    if low_price > open_price or low_price > high_price or low_price > close_price:
        raise ValueError("low must be less than or equal to open, high, and close")

    return MarketDataRow(
        timestamp=timestamp,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
        adjusted_close=adjusted_close,
    )


def parse_date(value: str | None) -> date:
    if not value:
        raise ValueError("date is required")

    try:
        return date.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError("date must use ISO format YYYY-MM-DD") from error


def parse_positive_decimal(value: str | None, field_name: str) -> Decimal:
    decimal_value = parse_decimal(value, field_name)
    if decimal_value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return decimal_value


def parse_optional_positive_decimal(value: str | None, field_name: str) -> Decimal | None:
    if value is None or not value.strip():
        return None
    return parse_positive_decimal(value, field_name)


def parse_decimal(value: str | None, field_name: str) -> Decimal:
    if value is None or not value.strip():
        raise ValueError(f"{field_name} is required")

    try:
        decimal_value = Decimal(value.strip())
    except InvalidOperation as error:
        raise ValueError(f"{field_name} must be a decimal number") from error

    if not decimal_value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return decimal_value


def parse_nonnegative_integer(value: str | None, field_name: str) -> int:
    if value is None or not value.strip():
        raise ValueError(f"{field_name} is required")

    try:
        integer_value = int(value.strip())
    except ValueError as error:
        raise ValueError(f"{field_name} must be an integer") from error

    if integer_value < 0:
        raise ValueError(f"{field_name} must be nonnegative")
    return integer_value


def batched(rows: Sequence[MarketDataRow], batch_size: int) -> Iterable[Sequence[MarketDataRow]]:
    for start in range(0, len(rows), batch_size):
        yield rows[start : start + batch_size]


def import_market_csv(
    path: Path,
    *,
    symbol: str = "SPY",
    interval: str = "1d",
    batch_size: int = DEFAULT_BATCH_SIZE,
    session: Session | None = None,
) -> ImportSummary:
    """Upsert a CSV into market_data and return a non-sensitive import summary."""

    if not path.is_file():
        raise ValueError(f"CSV file does not exist: {path}")
    if not symbol or symbol != symbol.upper() or len(symbol) > 20:
        raise ValueError("symbol must be an uppercase value between 1 and 20 characters")
    if interval != "1d":
        raise ValueError("interval must be 1d")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    rows, summary = parse_market_csv(path)
    database_session = session or SessionLocal()

    try:
        transaction = (
            database_session.begin_nested()
            if database_session.in_transaction()
            else database_session.begin()
        )
        with transaction:
            for batch in batched(rows, batch_size):
                batch_timestamps = [row.timestamp for row in batch]
                existing_timestamps = set(
                    database_session.scalars(
                        existing_timestamp_query(symbol, interval, batch_timestamps)
                    )
                )
                summary.updated_rows += len(existing_timestamps)
                summary.inserted_rows += len(batch) - len(existing_timestamps)
                execute_upsert(database_session, batch, symbol=symbol, interval=interval)

        summary.earliest_stored_timestamp = database_session.scalar(
            select(func.min(MarketData.timestamp)).where(
                MarketData.symbol == symbol,
                MarketData.interval == interval,
            )
        )
        summary.latest_stored_timestamp = database_session.scalar(
            select(func.max(MarketData.timestamp)).where(
                MarketData.symbol == symbol,
                MarketData.interval == interval,
            )
        )
        summary.total_symbol_rows = (
            database_session.scalar(
                select(func.count())
                .select_from(MarketData)
                .where(
                    MarketData.symbol == symbol,
                    MarketData.interval == interval,
                )
            )
            or 0
        )
        return summary
    except SQLAlchemyError:
        database_session.rollback()
        raise
    finally:
        if session is None:
            database_session.close()


def existing_timestamp_query(
    symbol: str,
    interval: str,
    timestamps: Sequence[datetime],
) -> Select[tuple[datetime]]:
    return select(MarketData.timestamp).where(
        MarketData.symbol == symbol,
        MarketData.interval == interval,
        MarketData.timestamp.in_(timestamps),
    )


def execute_upsert(
    session: Session,
    rows: Sequence[MarketDataRow],
    *,
    symbol: str,
    interval: str,
) -> None:
    values = [row.as_database_values(symbol=symbol, interval=interval) for row in rows]
    statement = insert(MarketData).values(values)
    statement = statement.on_conflict_do_update(
        index_elements=[MarketData.symbol, MarketData.interval, MarketData.timestamp],
        set_={
            "open_price": statement.excluded.open_price,
            "high_price": statement.excluded.high_price,
            "low_price": statement.excluded.low_price,
            "close_price": statement.excluded.close_price,
            "volume": statement.excluded.volume,
            "adjusted_close": statement.excluded.adjusted_close,
        },
    )
    session.execute(statement)


def format_summary(summary: ImportSummary) -> str:
    lines = [
        f"Total CSV rows: {summary.total_csv_rows}",
        f"Inserted rows: {summary.inserted_rows}",
        f"Updated rows: {summary.updated_rows}",
        f"Skipped rows: {summary.skipped_count}",
        f"Earliest stored timestamp: {format_timestamp(summary.earliest_stored_timestamp)}",
        f"Latest stored timestamp: {format_timestamp(summary.latest_stored_timestamp)}",
        f"Total symbol rows: {summary.total_symbol_rows}",
    ]
    return "\n".join(lines)


def format_timestamp(value: datetime | None) -> str:
    return value.astimezone(UTC).isoformat() if value else "none"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True, help="Path to a market-data CSV file")
    parser.add_argument("--symbol", default="SPY", help="Uppercase market symbol (default: SPY)")
    parser.add_argument("--interval", default="1d", help="Market interval (default: 1d)")
    parser.add_argument(
        "--batch-size",
        default=DEFAULT_BATCH_SIZE,
        type=int,
        help=f"Rows per database upsert batch (default: {DEFAULT_BATCH_SIZE})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = import_market_csv(
            args.file,
            symbol=args.symbol,
            interval=args.interval,
            batch_size=args.batch_size,
        )
    except (OSError, SQLAlchemyError, ValueError) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1

    for skipped_row in summary.skipped_rows[:MAX_REPORTED_SKIPPED_ROWS]:
        print(f"Skipped CSV row {skipped_row.row_number}: {skipped_row.reason}", file=sys.stderr)
    if summary.skipped_count > MAX_REPORTED_SKIPPED_ROWS:
        remaining = summary.skipped_count - MAX_REPORTED_SKIPPED_ROWS
        print(f"... {remaining} additional malformed rows skipped.", file=sys.stderr)

    print(format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
