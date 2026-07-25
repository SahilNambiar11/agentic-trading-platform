from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from app.backtesting.models import BacktestMetrics, CompletedTrade, EquityPoint, MarketBar


def calculate_metrics(
    *,
    bars: Sequence[MarketBar],
    equity_curve: Sequence[EquityPoint],
    completed_trades: Sequence[CompletedTrade],
    starting_cash: Decimal,
    final_portfolio_value: Decimal,
    buy_and_hold_start_index: int,
) -> BacktestMetrics:
    if not bars or not equity_curve:
        raise ValueError("bars and equity_curve are required")
    if not 0 <= buy_and_hold_start_index < len(bars):
        raise ValueError("buy_and_hold_start_index is outside the loaded data range")

    buy_and_hold_start_bar = bars[buy_and_hold_start_index]
    buy_and_hold_equity = calculate_buy_and_hold_equity_curve(
        bars,
        starting_cash=starting_cash,
        start_index=buy_and_hold_start_index,
    )
    buy_and_hold_final_value = buy_and_hold_equity[-1].equity
    winning_trades = sum(trade.profit_loss > 0 for trade in completed_trades)
    win_rate = (
        Decimal(winning_trades) / Decimal(len(completed_trades)) * Decimal("100")
        if completed_trades
        else Decimal("0")
    )

    return BacktestMetrics(
        total_return_percentage=(final_portfolio_value / starting_cash - Decimal("1"))
        * Decimal("100"),
        buy_and_hold_return_percentage=(buy_and_hold_final_value / starting_cash - Decimal("1"))
        * Decimal("100"),
        buy_and_hold_start_timestamp=buy_and_hold_start_bar.timestamp,
        buy_and_hold_start_price=buy_and_hold_start_bar.open_price,
        buy_and_hold_end_price=bars[-1].close_price,
        win_rate_percentage=win_rate,
        maximum_drawdown_percentage=calculate_maximum_drawdown(equity_curve),
        cagr_percentage=calculate_cagr(
            starting_cash,
            final_portfolio_value,
            bars[0].timestamp,
            bars[-1].timestamp,
        ),
    )


def calculate_buy_and_hold_equity_curve(
    bars: Sequence[MarketBar],
    *,
    starting_cash: Decimal,
    start_index: int,
) -> list[EquityPoint]:
    """Mark a whole-share benchmark to each close from the eligible entry bar."""

    if not 0 <= start_index < len(bars):
        raise ValueError("start_index is outside the loaded data range")
    start_bar = bars[start_index]
    quantity = int(starting_cash // start_bar.open_price)
    remaining_cash = starting_cash - Decimal(quantity) * start_bar.open_price
    return [
        EquityPoint(
            timestamp=bar.timestamp,
            equity=remaining_cash + Decimal(quantity) * bar.close_price,
        )
        for bar in bars[start_index:]
    ]


def calculate_maximum_drawdown(equity_curve: Sequence[EquityPoint]) -> Decimal:
    peak = equity_curve[0].equity
    maximum_drawdown = Decimal("0")
    for point in equity_curve:
        peak = max(peak, point.equity)
        drawdown = (point.equity / peak - Decimal("1")) * Decimal("100")
        maximum_drawdown = min(maximum_drawdown, drawdown)
    return maximum_drawdown


def calculate_cagr(
    starting_cash: Decimal,
    final_value: Decimal,
    start_timestamp: datetime,
    end_timestamp: datetime,
) -> Decimal | None:
    elapsed_days = Decimal(str((end_timestamp - start_timestamp).total_seconds())) / Decimal(
        "86400"
    )
    if elapsed_days <= 0:
        return None
    years = elapsed_days / Decimal("365.25")
    return ((final_value / starting_cash) ** (Decimal("1") / years) - Decimal("1")) * Decimal("100")
