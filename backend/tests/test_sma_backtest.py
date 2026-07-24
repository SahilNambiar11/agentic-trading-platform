from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.backtesting.engine import execute_long_only_signals
from app.backtesting.metrics import calculate_maximum_drawdown
from app.backtesting.models import EquityPoint, MarketBar, Signal, SignalType
from app.backtesting.sma_crossover import generate_sma_crossover_signals, simple_moving_averages


def bar(index: int, *, open_price: str, close_price: str | None = None) -> MarketBar:
    price = Decimal(close_price or open_price)
    return MarketBar(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index),
        open_price=Decimal(open_price),
        high_price=max(Decimal(open_price), price),
        low_price=min(Decimal(open_price), price),
        close_price=price,
        volume=100,
    )


def test_simple_moving_averages_and_insufficient_history() -> None:
    bars = [bar(index, open_price=str(index + 1)) for index in range(4)]

    assert simple_moving_averages(bars, 3) == [None, None, Decimal("2"), Decimal("3")]
    assert generate_sma_crossover_signals(bars[:2], short_window=2, long_window=3) == []


def test_exact_crossover_creates_one_signal_not_repeated_signals() -> None:
    bars = [
        bar(0, open_price="1"),
        bar(1, open_price="1"),
        bar(2, open_price="1"),
        bar(3, open_price="3"),
        bar(4, open_price="4"),
        bar(5, open_price="5"),
    ]

    signals = generate_sma_crossover_signals(bars, short_window=2, long_window=3)

    assert signals == [Signal(bars[3].timestamp, SignalType.BUY)]


def test_signal_executes_at_next_open_and_never_same_day() -> None:
    bars = [bar(0, open_price="10"), bar(1, open_price="10"), bar(2, open_price="20")]
    signal = Signal(bars[1].timestamp, SignalType.BUY)

    result = execute_long_only_signals(bars, [signal], starting_cash=Decimal("100"))

    assert result.completed_trades[0].entry_timestamp == bars[2].timestamp
    assert result.completed_trades[0].entry_price == Decimal("20")
    assert result.completed_trades[0].exit_reason == "end_of_data_liquidation"


def test_signal_on_final_bar_cannot_execute_same_day() -> None:
    bars = [bar(0, open_price="10"), bar(1, open_price="20")]

    result = execute_long_only_signals(
        bars,
        [Signal(bars[-1].timestamp, SignalType.BUY)],
        starting_cash=Decimal("100"),
    )

    assert result.completed_trades == []
    assert result.final_portfolio_value == Decimal("100")


def test_whole_share_sizing_leftover_cash_and_ignored_duplicate_buy() -> None:
    bars = [
        bar(0, open_price="10"),
        bar(1, open_price="30"),
        bar(2, open_price="40"),
        bar(3, open_price="40"),
    ]
    result = execute_long_only_signals(
        bars,
        [
            Signal(bars[0].timestamp, SignalType.BUY),
            Signal(bars[1].timestamp, SignalType.BUY),
        ],
        starting_cash=Decimal("100"),
    )

    assert result.completed_trades[0].quantity == 3
    assert result.final_portfolio_value == Decimal("130")
    assert result.ignored_signals == [Signal(bars[1].timestamp, SignalType.BUY)]


def test_sell_while_flat_is_ignored_and_signal_exit_calculates_profit() -> None:
    bars = [
        bar(0, open_price="10"),
        bar(1, open_price="10"),
        bar(2, open_price="20"),
        bar(3, open_price="25"),
    ]
    result = execute_long_only_signals(
        bars,
        [
            Signal(bars[0].timestamp, SignalType.SELL),
            Signal(bars[1].timestamp, SignalType.BUY),
            Signal(bars[2].timestamp, SignalType.SELL),
        ],
        starting_cash=Decimal("100"),
    )

    trade = result.completed_trades[0]
    assert result.ignored_signals == [Signal(bars[0].timestamp, SignalType.SELL)]
    assert trade.entry_price == Decimal("20")
    assert trade.exit_price == Decimal("25")
    assert trade.profit_loss == Decimal("25")
    assert trade.return_percentage == Decimal("25")
    assert trade.exit_reason == "signal"


def test_daily_equity_curve_and_maximum_drawdown() -> None:
    bars = [
        bar(0, open_price="10"),
        bar(1, open_price="10"),
        bar(2, open_price="10", close_price="15"),
        bar(3, open_price="10", close_price="9"),
    ]
    result = execute_long_only_signals(
        bars,
        [Signal(bars[1].timestamp, SignalType.BUY)],
        starting_cash=Decimal("100"),
    )

    assert [point.equity for point in result.equity_curve] == [
        Decimal("100"),
        Decimal("100"),
        Decimal("150"),
        Decimal("90"),
    ]
    assert calculate_maximum_drawdown(result.equity_curve) == Decimal("-40.0")


def test_known_drawdown_and_deterministic_execution() -> None:
    curve = [
        EquityPoint(datetime(2024, 1, 1, tzinfo=UTC), Decimal("100")),
        EquityPoint(datetime(2024, 1, 2, tzinfo=UTC), Decimal("120")),
        EquityPoint(datetime(2024, 1, 3, tzinfo=UTC), Decimal("90")),
    ]
    bars = [bar(0, open_price="10"), bar(1, open_price="10"), bar(2, open_price="20")]
    signals = [Signal(bars[1].timestamp, SignalType.BUY)]

    assert calculate_maximum_drawdown(curve) == Decimal("-25.00")
    assert execute_long_only_signals(
        bars, signals, starting_cash=Decimal("100")
    ) == execute_long_only_signals(
        bars,
        signals,
        starting_cash=Decimal("100"),
    )


def test_invalid_sma_window_order_is_rejected() -> None:
    with pytest.raises(ValueError, match="short_window"):
        generate_sma_crossover_signals([bar(0, open_price="1")], short_window=3, long_window=3)
