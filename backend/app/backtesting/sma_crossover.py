from collections.abc import Sequence
from decimal import Decimal

from app.backtesting.models import MarketBar, Signal, SignalType


def simple_moving_averages(
    bars: Sequence[MarketBar],
    window: int,
) -> list[Decimal | None]:
    """Calculate trailing close-price SMAs without look-ahead bias."""

    if window <= 0:
        raise ValueError("SMA window must be positive")

    averages: list[Decimal | None] = []
    rolling_total = Decimal("0")
    for index, bar in enumerate(bars):
        rolling_total += bar.close_price
        if index >= window:
            rolling_total -= bars[index - window].close_price
        averages.append(rolling_total / window if index >= window - 1 else None)
    return averages


def generate_sma_crossover_signals(
    bars: Sequence[MarketBar],
    *,
    short_window: int,
    long_window: int,
) -> list[Signal]:
    """Emit one signal for each exact close-price SMA crossover."""

    if short_window <= 0 or long_window <= 0:
        raise ValueError("SMA windows must be positive")
    if short_window >= long_window:
        raise ValueError("short_window must be less than long_window")

    short_smas = simple_moving_averages(bars, short_window)
    long_smas = simple_moving_averages(bars, long_window)
    signals: list[Signal] = []

    for index in range(1, len(bars)):
        previous_short = short_smas[index - 1]
        previous_long = long_smas[index - 1]
        current_short = short_smas[index]
        current_long = long_smas[index]
        if (
            previous_short is None
            or previous_long is None
            or current_short is None
            or current_long is None
        ):
            continue

        if previous_short <= previous_long and current_short > current_long:
            signals.append(Signal(bars[index].timestamp, SignalType.BUY))
        elif previous_short >= previous_long and current_short < current_long:
            signals.append(Signal(bars[index].timestamp, SignalType.SELL))

    return signals
