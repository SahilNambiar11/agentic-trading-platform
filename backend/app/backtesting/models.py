from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


@dataclass(frozen=True)
class MarketBar:
    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int


class SignalType(StrEnum):
    BUY = "buy"
    SELL = "sell"


class ExitReason(StrEnum):
    STRATEGY_EXIT = "strategy_exit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    FINAL_LIQUIDATION = "final_liquidation"


@dataclass(frozen=True)
class Signal:
    timestamp: datetime
    signal_type: SignalType


@dataclass(frozen=True)
class CompletedTrade:
    signal_timestamp: datetime
    entry_timestamp: datetime
    entry_price: Decimal
    quantity: int
    exit_signal_timestamp: datetime | None
    exit_timestamp: datetime
    exit_price: Decimal
    profit_loss: Decimal
    return_percentage: Decimal
    exit_reason: ExitReason


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    equity: Decimal


@dataclass(frozen=True)
class ExecutionResult:
    final_portfolio_value: Decimal
    total_realized_profit_loss: Decimal
    completed_trades: list[CompletedTrade]
    equity_curve: list[EquityPoint]
    ignored_signals: list[Signal]


@dataclass(frozen=True)
class BacktestMetrics:
    total_return_percentage: Decimal
    buy_and_hold_return_percentage: Decimal
    buy_and_hold_start_timestamp: datetime
    buy_and_hold_start_price: Decimal
    buy_and_hold_end_price: Decimal
    win_rate_percentage: Decimal
    maximum_drawdown_percentage: Decimal
    cagr_percentage: Decimal | None


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    interval: str
    data_start_timestamp: datetime
    data_end_timestamp: datetime
    bar_count: int
    first_sma_timestamp: datetime
    starting_cash: Decimal
    execution: ExecutionResult
    metrics: BacktestMetrics
