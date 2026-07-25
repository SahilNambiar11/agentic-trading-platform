from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.backtesting.engine import calculate_risk_levels, execute_long_only_signals
from app.backtesting.metrics import calculate_maximum_drawdown
from app.backtesting.models import EquityPoint, ExitReason, MarketBar, Signal, SignalType
from app.backtesting.sma_crossover import generate_sma_crossover_signals, simple_moving_averages


def bar(
    index: int,
    *,
    open_price: str,
    close_price: str | None = None,
    high_price: str | None = None,
    low_price: str | None = None,
) -> MarketBar:
    price = Decimal(close_price or open_price)
    return MarketBar(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index),
        open_price=Decimal(open_price),
        high_price=Decimal(high_price)
        if high_price is not None
        else max(Decimal(open_price), price),
        low_price=Decimal(low_price) if low_price is not None else min(Decimal(open_price), price),
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
    assert result.completed_trades[0].exit_reason is ExitReason.FINAL_LIQUIDATION


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
    assert trade.exit_reason is ExitReason.STRATEGY_EXIT


def test_risk_levels_are_calculated_from_actual_entry_fill() -> None:
    assert calculate_risk_levels(
        Decimal("123.45"),
        stop_loss_percent=Decimal("2"),
        take_profit_percent=Decimal("5"),
    ) == (Decimal("120.9810"), Decimal("129.6225"))


def test_stop_loss_and_take_profit_trigger_at_thresholds() -> None:
    entry_signal = Signal(bar(0, open_price="100").timestamp, SignalType.BUY)
    stop_bars = [
        bar(0, open_price="100"),
        bar(1, open_price="100", high_price="101", low_price="99"),
        bar(2, open_price="100", high_price="101", low_price="97"),
    ]
    take_bars = [
        bar(0, open_price="100"),
        bar(1, open_price="100", high_price="101", low_price="99"),
        bar(2, open_price="100", high_price="106", low_price="99"),
    ]

    stop = execute_long_only_signals(
        stop_bars,
        [entry_signal],
        starting_cash=Decimal("100"),
        stop_loss_percent=Decimal("2"),
    ).completed_trades[0]
    take = execute_long_only_signals(
        take_bars,
        [entry_signal],
        starting_cash=Decimal("100"),
        take_profit_percent=Decimal("5"),
    ).completed_trades[0]

    assert (stop.exit_price, stop.exit_reason) == (
        Decimal("98.00"),
        ExitReason.STOP_LOSS,
    )
    assert (take.exit_price, take.exit_reason) == (
        Decimal("105.00"),
        ExitReason.TAKE_PROFIT,
    )


def test_opening_gaps_fill_at_open() -> None:
    buy = Signal(bar(0, open_price="100").timestamp, SignalType.BUY)
    stop = execute_long_only_signals(
        [
            bar(0, open_price="100"),
            bar(1, open_price="100"),
            bar(2, open_price="95"),
        ],
        [buy],
        starting_cash=Decimal("100"),
        stop_loss_percent=Decimal("2"),
    ).completed_trades[0]
    take = execute_long_only_signals(
        [
            bar(0, open_price="100"),
            bar(1, open_price="100"),
            bar(2, open_price="110"),
        ],
        [buy],
        starting_cash=Decimal("100"),
        take_profit_percent=Decimal("5"),
    ).completed_trades[0]

    assert stop.exit_price == Decimal("95")
    assert stop.exit_reason is ExitReason.STOP_LOSS
    assert take.exit_price == Decimal("110")
    assert take.exit_reason is ExitReason.TAKE_PROFIT


def test_entry_bar_cannot_trigger_and_both_intraday_thresholds_choose_stop() -> None:
    bars = [
        bar(0, open_price="100"),
        bar(1, open_price="100", high_price="110", low_price="90"),
        bar(2, open_price="100", high_price="110", low_price="90"),
    ]
    result = execute_long_only_signals(
        bars,
        [Signal(bars[0].timestamp, SignalType.BUY)],
        starting_cash=Decimal("100"),
        stop_loss_percent=Decimal("2"),
        take_profit_percent=Decimal("5"),
    )

    trade = result.completed_trades[0]
    assert trade.entry_timestamp == bars[1].timestamp
    assert trade.exit_timestamp == bars[2].timestamp
    assert trade.exit_price == Decimal("98.00")
    assert trade.exit_reason is ExitReason.STOP_LOSS


def test_risk_exit_precedes_pending_strategy_exit_at_open() -> None:
    bars = [
        bar(0, open_price="100"),
        bar(1, open_price="100"),
        bar(2, open_price="95"),
    ]
    signals = [
        Signal(bars[0].timestamp, SignalType.BUY),
        Signal(bars[1].timestamp, SignalType.SELL),
    ]

    result = execute_long_only_signals(
        bars,
        signals,
        starting_cash=Decimal("100"),
        stop_loss_percent=Decimal("2"),
    )

    assert result.completed_trades[0].exit_reason is ExitReason.STOP_LOSS
    assert result.completed_trades[0].exit_signal_timestamp is None
    assert result.ignored_signals == [signals[1]]


def test_no_risk_controls_preserve_execution_except_normalized_exit_reasons() -> None:
    bars = [
        bar(0, open_price="10"),
        bar(1, open_price="10", close_price="11"),
        bar(2, open_price="12", close_price="13"),
        bar(3, open_price="14", close_price="15"),
    ]
    signals = [
        Signal(bars[0].timestamp, SignalType.BUY),
        Signal(bars[2].timestamp, SignalType.SELL),
    ]

    omitted = execute_long_only_signals(
        bars,
        signals,
        starting_cash=Decimal("100"),
    )
    explicit_none = execute_long_only_signals(
        bars,
        signals,
        starting_cash=Decimal("100"),
        stop_loss_percent=None,
        take_profit_percent=None,
    )

    assert omitted == explicit_none


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
