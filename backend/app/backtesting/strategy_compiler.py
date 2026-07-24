"""Compile validated strategy specifications into deterministic signals."""

from collections.abc import Sequence
from decimal import Decimal

from app.backtesting.models import MarketBar, Signal, SignalType
from app.backtesting.sma_crossover import simple_moving_averages
from app.schemas.strategy_spec import (
    Condition,
    ConstantOperand,
    IndicatorName,
    IndicatorOperand,
    Operand,
    Operator,
    PriceOperand,
    StrategySpecification,
)
from app.services.strategy_semantics import validate_strategy_semantics


class StrategyCompilationError(ValueError):
    """Raised when a validated specification cannot be deterministically evaluated."""


class CompiledStrategy:
    def __init__(self, specification: StrategySpecification) -> None:
        self.specification = specification

    def generate_signals(self, bars: Sequence[MarketBar]) -> list[Signal]:
        entry_values = evaluate_condition(self.specification.entry, bars)
        exit_values = evaluate_condition(self.specification.exit, bars)
        signals: list[Signal] = []
        for index, bar in enumerate(bars):
            if entry_values[index]:
                signals.append(Signal(bar.timestamp, SignalType.BUY))
            if exit_values[index]:
                signals.append(Signal(bar.timestamp, SignalType.SELL))
        return signals

    def first_signal_eligible_index(self, bars: Sequence[MarketBar]) -> int:
        return max(
            condition_first_eligible_index(self.specification.entry),
            condition_first_eligible_index(self.specification.exit),
            0,
        )


def compile_strategy(specification: StrategySpecification) -> CompiledStrategy:
    validate_strategy_semantics(specification)
    return CompiledStrategy(specification)


def evaluate_condition(condition: Condition, bars: Sequence[MarketBar]) -> list[bool]:
    left = evaluate_operand(condition.left, bars)
    right = evaluate_operand(condition.right, bars)
    values = [False] * len(bars)
    for index in range(len(bars)):
        if condition.operator in {Operator.CROSSES_ABOVE, Operator.CROSSES_BELOW}:
            if index == 0:
                continue
            previous_left, previous_right = left[index - 1], right[index - 1]
            current_left, current_right = left[index], right[index]
            if None in (previous_left, previous_right, current_left, current_right):
                continue
            assert previous_left is not None
            assert previous_right is not None
            assert current_left is not None
            assert current_right is not None
            if condition.operator is Operator.CROSSES_ABOVE:
                values[index] = previous_left <= previous_right and current_left > current_right
            else:
                values[index] = previous_left >= previous_right and current_left < current_right
            continue

        current_left, current_right = left[index], right[index]
        if current_left is None or current_right is None:
            continue
        values[index] = compare(current_left, current_right, condition.operator)
    return values


def evaluate_operand(operand: Operand, bars: Sequence[MarketBar]) -> list[Decimal | None]:
    if isinstance(operand, PriceOperand):
        return [bar.close_price for bar in bars]
    if isinstance(operand, ConstantOperand):
        return [operand.value for _ in bars]
    if operand.name is IndicatorName.SMA:
        return simple_moving_averages(bars, operand.period)
    if operand.name is IndicatorName.EMA:
        return exponential_moving_averages(bars, operand.period)
    raise StrategyCompilationError("Unsupported strategy operand.")


def exponential_moving_averages(
    bars: Sequence[MarketBar],
    window: int,
) -> list[Decimal | None]:
    if window <= 0:
        raise StrategyCompilationError("EMA window must be positive.")
    values: list[Decimal | None] = [None] * len(bars)
    if len(bars) < window:
        return values

    first = sum((bar.close_price for bar in bars[:window]), Decimal("0")) / Decimal(window)
    values[window - 1] = first
    multiplier = Decimal("2") / Decimal(window + 1)
    previous = first
    for index in range(window, len(bars)):
        previous = (bars[index].close_price - previous) * multiplier + previous
        values[index] = previous
    return values


def compare(left: Decimal, right: Decimal, operator: Operator) -> bool:
    comparisons = {
        Operator.GREATER_THAN: left > right,
        Operator.LESS_THAN: left < right,
        Operator.GREATER_THAN_OR_EQUAL: left >= right,
        Operator.LESS_THAN_OR_EQUAL: left <= right,
    }
    try:
        return comparisons[operator]
    except KeyError as error:
        raise StrategyCompilationError("Unsupported comparison operator.") from error


def condition_first_eligible_index(condition: Condition) -> int:
    warmup_index = max(
        operand_first_evaluable_index(condition.left),
        operand_first_evaluable_index(condition.right),
    )
    if condition.operator in {Operator.CROSSES_ABOVE, Operator.CROSSES_BELOW}:
        return warmup_index + 1
    return warmup_index


def operand_first_evaluable_index(operand: Operand) -> int:
    if isinstance(operand, IndicatorOperand):
        return operand.period - 1
    return 0
