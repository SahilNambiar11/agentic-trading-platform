from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.backtesting.models import MarketBar
from app.backtesting.sma_crossover import generate_sma_crossover_signals
from app.backtesting.strategy_compiler import (
    compile_strategy,
    evaluate_condition,
    exponential_moving_averages,
)
from app.schemas.strategy_spec import (
    Condition,
    ConstantOperand,
    ExecutionSettings,
    IndicatorName,
    IndicatorOperand,
    Operator,
    PriceOperand,
    StrategySpecification,
)


def bar(index: int, close: str) -> MarketBar:
    price = Decimal(close)
    return MarketBar(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index),
        open_price=price,
        high_price=price,
        low_price=price,
        close_price=price,
        volume=1,
    )


def crossover_specification() -> StrategySpecification:
    short = IndicatorOperand(type="indicator", name=IndicatorName.SMA, source="close", period=2)
    long = IndicatorOperand(type="indicator", name=IndicatorName.SMA, source="close", period=3)
    return StrategySpecification(
        symbol="SPY",
        interval="1d",
        entry=Condition(left=short, operator=Operator.CROSSES_ABOVE, right=long),
        exit=Condition(left=short, operator=Operator.CROSSES_BELOW, right=long),
        execution=ExecutionSettings(
            direction="long", position_size_percent=100, signal_execution="next_bar_open"
        ),
    )


def test_compiled_sma_crossover_matches_hardcoded_signals() -> None:
    bars = [bar(index, value) for index, value in enumerate(["1", "1", "1", "3", "4", "5", "1"])]

    compiled = compile_strategy(crossover_specification())

    assert compiled.generate_signals(bars) == generate_sma_crossover_signals(
        bars, short_window=2, long_window=3
    )
    assert compiled.first_signal_eligible_index(bars) == 3


def test_ema_close_constant_and_all_comparison_operators() -> None:
    bars = [bar(0, "1"), bar(1, "2"), bar(2, "3")]
    ema = IndicatorOperand(type="indicator", name=IndicatorName.EMA, source="close", period=2)
    constant = ConstantOperand(type="constant", value=Decimal("1.5"))
    assert exponential_moving_averages(bars, 2) == [None, Decimal("1.5"), Decimal("2.5")]
    expected = {
        Operator.GREATER_THAN: [False, False, True],
        Operator.LESS_THAN: [False, False, False],
        Operator.GREATER_THAN_OR_EQUAL: [False, True, True],
        Operator.LESS_THAN_OR_EQUAL: [False, True, False],
    }
    for operator, values in expected.items():
        condition = Condition(left=ema, operator=operator, right=constant)
        assert evaluate_condition(condition, bars) == values


def test_cross_boundaries_are_exact() -> None:
    bars = [bar(0, "1"), bar(1, "1"), bar(2, "2")]
    condition = Condition(
        left=PriceOperand(type="price", source="close"),
        operator=Operator.CROSSES_ABOVE,
        right=ConstantOperand(type="constant", value=Decimal("1")),
    )
    assert evaluate_condition(condition, bars) == [False, False, True]
