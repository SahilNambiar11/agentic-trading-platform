from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from app.backtesting.models import (
    CompletedTrade,
    EquityPoint,
    ExecutionResult,
    ExitReason,
    MarketBar,
    Signal,
    SignalType,
)


def execute_long_only_signals(
    bars: Sequence[MarketBar],
    signals: Sequence[Signal],
    *,
    starting_cash: Decimal,
    stop_loss_percent: Decimal | None = None,
    take_profit_percent: Decimal | None = None,
) -> ExecutionResult:
    """Execute signals and optional position-level risk controls deterministically."""

    if starting_cash <= 0:
        raise ValueError("starting_cash must be positive")
    if not bars:
        raise ValueError("at least one market bar is required")
    validate_risk_control(stop_loss_percent, "stop_loss_percent")
    validate_risk_control(take_profit_percent, "take_profit_percent")

    signals_by_timestamp: dict[object, list[Signal]] = defaultdict(list)
    for signal in signals:
        signals_by_timestamp[signal.timestamp].append(signal)

    cash = starting_cash
    quantity = 0
    entry_price: Decimal | None = None
    entry_timestamp = None
    entry_signal_timestamp = None
    entry_bar_index: int | None = None
    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    completed_trades: list[CompletedTrade] = []
    equity_curve: list[EquityPoint] = []
    ignored_signals: list[Signal] = []

    for index, bar in enumerate(bars):
        position_closed_at_open = False
        if index > 0:
            pending_signals = signals_by_timestamp[bars[index - 1].timestamp]
            opening_risk_exit = evaluate_opening_risk_exit(
                bar,
                quantity=quantity,
                entry_bar_index=entry_bar_index,
                current_bar_index=index,
                stop_price=stop_price,
                take_profit_price=take_profit_price,
            )
            if opening_risk_exit is not None:
                exit_price, exit_reason = opening_risk_exit
                cash, completed_trade = close_position(
                    bar=bar,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    cash=cash,
                    quantity=quantity,
                    entry_price=entry_price,
                    entry_timestamp=entry_timestamp,
                    entry_signal_timestamp=entry_signal_timestamp,
                )
                completed_trades.append(completed_trade)
                quantity = 0
                position_closed_at_open = True
                ignored_signals.extend(pending_signals)
                (
                    entry_price,
                    entry_timestamp,
                    entry_signal_timestamp,
                    entry_bar_index,
                    stop_price,
                    take_profit_price,
                ) = cleared_position()
            else:
                for signal in pending_signals:
                    if signal.signal_type is SignalType.BUY:
                        was_flat = quantity == 0
                        (
                            cash,
                            quantity,
                            entry_price,
                            entry_timestamp,
                            entry_signal_timestamp,
                        ) = execute_buy(
                            signal,
                            bar,
                            cash=cash,
                            quantity=quantity,
                            entry_price=entry_price,
                            entry_timestamp=entry_timestamp,
                            entry_signal_timestamp=entry_signal_timestamp,
                            ignored_signals=ignored_signals,
                        )
                        if was_flat and quantity > 0 and entry_price is not None:
                            entry_bar_index = index
                            stop_price, take_profit_price = calculate_risk_levels(
                                entry_price,
                                stop_loss_percent=stop_loss_percent,
                                take_profit_percent=take_profit_percent,
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
                            (
                                entry_price,
                                entry_timestamp,
                                entry_signal_timestamp,
                                entry_bar_index,
                                stop_price,
                                take_profit_price,
                            ) = cleared_position()
                            position_closed_at_open = True

        if quantity > 0 and not position_closed_at_open:
            intraday_risk_exit = evaluate_intraday_risk_exit(
                bar,
                quantity=quantity,
                entry_bar_index=entry_bar_index,
                current_bar_index=index,
                stop_price=stop_price,
                take_profit_price=take_profit_price,
            )
            if intraday_risk_exit is not None:
                exit_price, exit_reason = intraday_risk_exit
                cash, completed_trade = close_position(
                    bar=bar,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    cash=cash,
                    quantity=quantity,
                    entry_price=entry_price,
                    entry_timestamp=entry_timestamp,
                    entry_signal_timestamp=entry_signal_timestamp,
                )
                completed_trades.append(completed_trade)
                quantity = 0
                (
                    entry_price,
                    entry_timestamp,
                    entry_signal_timestamp,
                    entry_bar_index,
                    stop_price,
                    take_profit_price,
                ) = cleared_position()

        equity_curve.append(EquityPoint(bar.timestamp, cash + quantity * bar.close_price))

    if quantity > 0:
        final_bar = bars[-1]
        cash, completed_trade = close_position(
            bar=final_bar,
            exit_price=final_bar.close_price,
            exit_reason=ExitReason.FINAL_LIQUIDATION,
            cash=cash,
            quantity=quantity,
            entry_price=entry_price,
            entry_timestamp=entry_timestamp,
            entry_signal_timestamp=entry_signal_timestamp,
        )
        completed_trades.append(completed_trade)

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
            exit_reason=ExitReason.STRATEGY_EXIT,
        ),
    )


def calculate_risk_levels(
    entry_price: Decimal,
    *,
    stop_loss_percent: Decimal | None,
    take_profit_percent: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    hundred = Decimal("100")
    stop_price = (
        entry_price * (Decimal("1") - stop_loss_percent / hundred)
        if stop_loss_percent is not None
        else None
    )
    take_profit_price = (
        entry_price * (Decimal("1") + take_profit_percent / hundred)
        if take_profit_percent is not None
        else None
    )
    return stop_price, take_profit_price


def evaluate_opening_risk_exit(
    bar: MarketBar,
    *,
    quantity: int,
    entry_bar_index: int | None,
    current_bar_index: int,
    stop_price: Decimal | None,
    take_profit_price: Decimal | None,
) -> tuple[Decimal, ExitReason] | None:
    if quantity == 0 or entry_bar_index is None or current_bar_index <= entry_bar_index:
        return None
    if stop_price is not None and bar.open_price <= stop_price:
        return bar.open_price, ExitReason.STOP_LOSS
    if take_profit_price is not None and bar.open_price >= take_profit_price:
        return bar.open_price, ExitReason.TAKE_PROFIT
    return None


def evaluate_intraday_risk_exit(
    bar: MarketBar,
    *,
    quantity: int,
    entry_bar_index: int | None,
    current_bar_index: int,
    stop_price: Decimal | None,
    take_profit_price: Decimal | None,
) -> tuple[Decimal, ExitReason] | None:
    if quantity == 0 or entry_bar_index is None or current_bar_index <= entry_bar_index:
        return None
    if stop_price is not None and bar.low_price <= stop_price:
        return stop_price, ExitReason.STOP_LOSS
    if take_profit_price is not None and bar.high_price >= take_profit_price:
        return take_profit_price, ExitReason.TAKE_PROFIT
    return None


def close_position(
    *,
    bar: MarketBar,
    exit_price: Decimal,
    exit_reason: ExitReason,
    cash: Decimal,
    quantity: int,
    entry_price: Decimal | None,
    entry_timestamp: datetime | None,
    entry_signal_timestamp: datetime | None,
    exit_signal_timestamp: datetime | None = None,
) -> tuple[Decimal, CompletedTrade]:
    if quantity <= 0:
        raise RuntimeError("cannot close a flat position")
    if entry_price is None or entry_timestamp is None or entry_signal_timestamp is None:
        raise RuntimeError("open position is missing entry details")

    proceeds = Decimal(quantity) * exit_price
    cost = Decimal(quantity) * entry_price
    profit_loss = proceeds - cost
    return (
        cash + proceeds,
        CompletedTrade(
            signal_timestamp=entry_signal_timestamp,
            entry_timestamp=entry_timestamp,
            entry_price=entry_price,
            quantity=quantity,
            exit_signal_timestamp=exit_signal_timestamp,
            exit_timestamp=bar.timestamp,
            exit_price=exit_price,
            profit_loss=profit_loss,
            return_percentage=profit_loss / cost * Decimal("100"),
            exit_reason=exit_reason,
        ),
    )


def cleared_position() -> tuple[
    None,
    None,
    None,
    None,
    None,
    None,
]:
    return None, None, None, None, None, None


def validate_risk_control(value: Decimal | None, field_name: str) -> None:
    if value is not None and (not value.is_finite() or value <= 0):
        raise ValueError(f"{field_name} must be finite and positive")
