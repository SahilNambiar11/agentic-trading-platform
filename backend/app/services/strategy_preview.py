"""Deterministic backtest previews for parsed strategies."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.backtesting.engine import execute_long_only_signals
from app.backtesting.market_data import load_market_bars
from app.backtesting.metrics import calculate_buy_and_hold_equity_curve, calculate_metrics
from app.backtesting.models import BacktestMetrics, EquityPoint, ExecutionResult, MarketBar
from app.backtesting.strategy_compiler import compile_strategy
from app.schemas.strategy_spec import ParsedStrategyResult, StrategySpecification
from app.services.strategy_interpretation import interpret_strategy

STARTING_CASH = Decimal("10000")


class MarketDataUnavailableError(ValueError):
    pass


class StrategyPreview:
    def __init__(
        self,
        *,
        parsed_strategy: ParsedStrategyResult,
        interpretation: str,
        execution: ExecutionResult,
        metrics: BacktestMetrics,
        bar_count: int,
        start_timestamp: datetime,
        end_timestamp: datetime,
        bars: list[MarketBar],
        comparison_start_index: int,
        buy_and_hold_equity_curve: list[EquityPoint],
    ) -> None:
        self.parsed_strategy = parsed_strategy
        self.interpretation = interpretation
        self.execution = execution
        self.metrics = metrics
        self.bar_count = bar_count
        self.start_timestamp = start_timestamp
        self.end_timestamp = end_timestamp
        self.bars = bars
        self.comparison_start_index = comparison_start_index
        self.buy_and_hold_equity_curve = buy_and_hold_equity_curve


def create_preview(
    session: Session,
    parsed_strategy: ParsedStrategyResult,
) -> StrategyPreview:
    return create_specification_preview(session, parsed_strategy.specification, parsed_strategy)


def create_specification_preview(
    session: Session,
    specification: StrategySpecification,
    parsed_strategy: ParsedStrategyResult,
) -> StrategyPreview:
    compiled = compile_strategy(specification)
    bars = load_market_bars(session, symbol=specification.symbol, interval=specification.interval)
    eligible_index = compiled.first_signal_eligible_index(bars)
    if not bars or eligible_index >= len(bars):
        raise MarketDataUnavailableError(
            "Not enough SPY daily market data is available for this strategy."
        )
    execution = execute_long_only_signals(
        bars,
        compiled.generate_signals(bars),
        starting_cash=STARTING_CASH,
        stop_loss_percent=specification.stop_loss_percent,
        take_profit_percent=specification.take_profit_percent,
    )
    metrics = calculate_metrics(
        bars=bars,
        equity_curve=execution.equity_curve,
        completed_trades=execution.completed_trades,
        starting_cash=STARTING_CASH,
        final_portfolio_value=execution.final_portfolio_value,
        buy_and_hold_start_index=eligible_index,
    )
    buy_and_hold_equity_curve = calculate_buy_and_hold_equity_curve(
        bars,
        starting_cash=STARTING_CASH,
        start_index=eligible_index,
    )
    # The comparison chart begins at the shared allocation point. Subsequent
    # benchmark points are marked to each daily close.
    buy_and_hold_equity_curve[0] = EquityPoint(
        timestamp=bars[eligible_index].timestamp,
        equity=STARTING_CASH,
    )
    return StrategyPreview(
        parsed_strategy=parsed_strategy,
        interpretation=interpret_strategy(parsed_strategy),
        execution=execution,
        metrics=metrics,
        bar_count=len(bars),
        start_timestamp=bars[0].timestamp,
        end_timestamp=bars[-1].timestamp,
        bars=bars,
        comparison_start_index=eligible_index,
        buy_and_hold_equity_curve=buy_and_hold_equity_curve,
    )
