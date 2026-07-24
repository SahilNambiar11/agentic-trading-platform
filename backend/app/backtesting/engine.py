from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from app.backtesting.models import (
    CompletedTrade,
    EquityPoint,
    ExecutionResult,
    MarketBar,
    Signal,
    SignalType,
)


def execute_long_only_signals(
    bars: Sequence[MarketBar],
    signals: Sequence[Signal],
    *,
    starting_cash: Decimal,
) -> ExecutionResult:
    """Execute prior-close signals at the next bar's open without leverage."""

    if starting_cash <= 0:
        raise ValueError("starting_cash must be positive")
    if not bars:
        raise ValueError("at least one market bar is required")

    signals_by_timestamp: dict[object, list[Signal]] = defaultdict(list)
    for signal in signals:
        signals_by_timestamp[signal.timestamp].append(signal)

    cash = starting_cash
    quantity = 0
    entry_price: Decimal | None = None
    entry_timestamp = None
    entry_signal_timestamp = None
    completed_trades: list[CompletedTrade] = []
    equity_curve: list[EquityPoint] = []
    ignored_signals: list[Signal] = []

    for index, bar in enumerate(bars):
        if index > 0:
            for signal in signals_by_timestamp[bars[index - 1].timestamp]:
                if signal.signal_type is SignalType.BUY:
                    cash, quantity, entry_price, entry_timestamp, entry_signal_timestamp = (
                        execute_buy(
                            signal,
                            bar,
                            cash=cash,
                            quantity=quantity,
                            entry_price=entry_price,
                            entry_timestamp=entry_timestamp,
                            entry_signal_timestamp=entry_signal_timestamp,
                            ignored_signals=ignored_signals,
                        )
                    )
                else:
                    cash, quantity, completed_trade = execute_sell(
                        signal,
                        bar,
                        cash=cash,
                        quantity=quantity,
                        entry_price=entry_price,
                        entry_timestamp=entry_timestamp,
                        entry_signal_timestamp=entry_signal_timestamp,
                        ignored_signals=ignored_signals,
                    )
                    if completed_trade is not None:
                        completed_trades.append(completed_trade)
                        entry_price = None
                        entry_timestamp = None
                        entry_signal_timestamp = None

        equity_curve.append(EquityPoint(bar.timestamp, cash + quantity * bar.close_price))

    if quantity > 0:
        final_bar = bars[-1]
        if entry_price is None or entry_timestamp is None or entry_signal_timestamp is None:
            raise RuntimeError("open position is missing entry details")
        proceeds = Decimal(quantity) * final_bar.close_price
        profit_loss = proceeds - Decimal(quantity) * entry_price
        completed_trades.append(
            CompletedTrade(
                signal_timestamp=entry_signal_timestamp,
                entry_timestamp=entry_timestamp,
                entry_price=entry_price,
                quantity=quantity,
                exit_signal_timestamp=None,
                exit_timestamp=final_bar.timestamp,
                exit_price=final_bar.close_price,
                profit_loss=profit_loss,
                return_percentage=profit_loss / (Decimal(quantity) * entry_price) * Decimal("100"),
                exit_reason="end_of_data_liquidation",
            )
        )
        cash += proceeds

    return ExecutionResult(
        final_portfolio_value=cash,
        total_realized_profit_loss=sum(
            (trade.profit_loss for trade in completed_trades), Decimal("0")
        ),
        completed_trades=completed_trades,
        equity_curve=equity_curve,
        ignored_signals=ignored_signals,
    )


def execute_buy(
    signal: Signal,
    bar: MarketBar,
    *,
    cash: Decimal,
    quantity: int,
    entry_price: Decimal | None,
    entry_timestamp: datetime | None,
    entry_signal_timestamp: datetime | None,
    ignored_signals: list[Signal],
) -> tuple[Decimal, int, Decimal | None, datetime | None, datetime | None]:
    if quantity > 0:
        ignored_signals.append(signal)
        return cash, quantity, entry_price, entry_timestamp, entry_signal_timestamp

    shares_to_buy = int(cash // bar.open_price)
    if shares_to_buy == 0:
        ignored_signals.append(signal)
        return cash, quantity, entry_price, entry_timestamp, entry_signal_timestamp

    return (
        cash - Decimal(shares_to_buy) * bar.open_price,
        shares_to_buy,
        bar.open_price,
        bar.timestamp,
        signal.timestamp,
    )


def execute_sell(
    signal: Signal,
    bar: MarketBar,
    *,
    cash: Decimal,
    quantity: int,
    entry_price: Decimal | None,
    entry_timestamp: datetime | None,
    entry_signal_timestamp: datetime | None,
    ignored_signals: list[Signal],
) -> tuple[Decimal, int, CompletedTrade | None]:
    if quantity == 0:
        ignored_signals.append(signal)
        return cash, quantity, None
    if entry_price is None or entry_timestamp is None or entry_signal_timestamp is None:
        raise RuntimeError("open position is missing entry details")

    proceeds = Decimal(quantity) * bar.open_price
    profit_loss = proceeds - Decimal(quantity) * entry_price
    return (
        cash + proceeds,
        0,
        CompletedTrade(
            signal_timestamp=entry_signal_timestamp,
            entry_timestamp=entry_timestamp,
            entry_price=entry_price,
            quantity=quantity,
            exit_signal_timestamp=signal.timestamp,
            exit_timestamp=bar.timestamp,
            exit_price=bar.open_price,
            profit_loss=profit_loss,
            return_percentage=profit_loss / (Decimal(quantity) * entry_price) * Decimal("100"),
            exit_reason="signal",
        ),
    )
