"""Run a deterministic long-only SMA crossover backtest against market_data."""

from __future__ import annotations

import argparse
from decimal import Decimal

from app.backtesting.engine import execute_long_only_signals
from app.backtesting.market_data import load_market_bars
from app.backtesting.metrics import calculate_metrics
from app.backtesting.models import BacktestResult, CompletedTrade
from app.backtesting.sma_crossover import generate_sma_crossover_signals
from app.db.session import SessionLocal


def run_sma_backtest(
    *,
    symbol: str,
    interval: str,
    short_window: int,
    long_window: int,
    starting_cash: Decimal,
) -> BacktestResult:
    """Run the requested deterministic close-signal/next-open SMA strategy."""

    if short_window >= long_window:
        raise ValueError("short_window must be less than long_window")

    with SessionLocal() as session:
        bars = load_market_bars(session, symbol=symbol, interval=interval)

    if len(bars) <= long_window:
        raise ValueError("not enough bars to calculate both SMAs and execute a next-day signal")

    signals = generate_sma_crossover_signals(
        bars,
        short_window=short_window,
        long_window=long_window,
    )
    execution = execute_long_only_signals(bars, signals, starting_cash=starting_cash)
    first_sma_timestamp = bars[long_window - 1].timestamp
    metrics = calculate_metrics(
        bars=bars,
        equity_curve=execution.equity_curve,
        completed_trades=execution.completed_trades,
        starting_cash=starting_cash,
        final_portfolio_value=execution.final_portfolio_value,
        buy_and_hold_start_index=long_window,
    )
    return BacktestResult(
        symbol=symbol,
        interval=interval,
        data_start_timestamp=bars[0].timestamp,
        data_end_timestamp=bars[-1].timestamp,
        bar_count=len(bars),
        first_sma_timestamp=first_sma_timestamp,
        starting_cash=starting_cash,
        execution=execution,
        metrics=metrics,
    )


def format_money(value: Decimal) -> str:
    return f"${value:,.2f}"


def format_percentage(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def format_trade(index: int, trade: CompletedTrade) -> str:
    exit_signal = trade.exit_signal_timestamp.isoformat() if trade.exit_signal_timestamp else "none"
    return "\n".join(
        [
            f"Trade {index}",
            f"  Signal timestamp: {trade.signal_timestamp.isoformat()}",
            f"  Entry timestamp: {trade.entry_timestamp.isoformat()}",
            f"  Entry price: {format_money(trade.entry_price)}",
            f"  Quantity: {trade.quantity}",
            f"  Exit signal timestamp: {exit_signal}",
            f"  Exit timestamp: {trade.exit_timestamp.isoformat()}",
            f"  Exit price: {format_money(trade.exit_price)}",
            f"  Profit/loss: {format_money(trade.profit_loss)}",
            f"  Return: {format_percentage(trade.return_percentage)}",
            f"  Exit reason: {trade.exit_reason}",
        ]
    )


def format_result(result: BacktestResult) -> str:
    metrics = result.metrics
    lines = [
        f"Symbol: {result.symbol}",
        f"Interval: {result.interval}",
        f"Data start: {result.data_start_timestamp.isoformat()}",
        f"Data end: {result.data_end_timestamp.isoformat()}",
        f"Bars loaded: {result.bar_count}",
        f"First timestamp where both SMAs are available: {result.first_sma_timestamp.isoformat()}",
        f"Starting cash: {format_money(result.starting_cash)}",
        f"Final portfolio value: {format_money(result.execution.final_portfolio_value)}",
        f"Total return: {format_percentage(metrics.total_return_percentage)}",
        "Buy-and-hold window: "
        f"buy at {metrics.buy_and_hold_start_timestamp.isoformat()} open "
        f"({format_money(metrics.buy_and_hold_start_price)}), value at final close "
        f"({format_money(metrics.buy_and_hold_end_price)})",
        f"Buy-and-hold return: {format_percentage(metrics.buy_and_hold_return_percentage)}",
        f"Completed trades: {len(result.execution.completed_trades)}",
        f"Win rate: {format_percentage(metrics.win_rate_percentage)}",
        f"Total realized profit/loss: {format_money(result.execution.total_realized_profit_loss)}",
        f"Maximum drawdown: {format_percentage(metrics.maximum_drawdown_percentage)}",
        f"CAGR: {format_percentage(metrics.cagr_percentage)}",
        "Trades:",
    ]
    lines.extend(
        format_trade(index, trade)
        for index, trade in enumerate(result.execution.completed_trades, start=1)
    )
    if not result.execution.completed_trades:
        lines.append("  No completed trades.")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--short-window", default=50, type=int)
    parser.add_argument("--long-window", default=200, type=int)
    parser.add_argument("--starting-cash", default=Decimal("10000"), type=Decimal)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_sma_backtest(
        symbol=args.symbol,
        interval=args.interval,
        short_window=args.short_window,
        long_window=args.long_window,
        starting_cash=args.starting_cash,
    )
    print(format_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
