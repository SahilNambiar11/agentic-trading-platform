import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.strategy_spec import (
    ConditionDraft,
    IndicatorName,
    IndicatorOperand,
    OperandDraft,
    Operator,
    StrategyParseDraft,
)
from app.services.strategy_interpretation import interpret_strategy
from app.services.strategy_parser import (
    OpenAIStrategyParser,
    StrategyMalformedOutputError,
    StrategyParserError,
    StrategyProviderError,
    StrategyProviderRefusalError,
    StrategyProviderTimeoutError,
    normalize_strategy_draft,
)
from app.services.strategy_semantics import StrategyValidationError


def crossover(
    operator: Operator,
    *,
    short_name: IndicatorName | None = IndicatorName.SMA,
    short_period: int | None = 50,
    long_period: int | None = 200,
) -> ConditionDraft:
    return ConditionDraft(
        left=OperandDraft(
            type="indicator",
            name=short_name,
            period=short_period,
        ),
        operator=operator,
        right=OperandDraft(
            type="indicator",
            name=short_name,
            period=long_period,
        ),
    )


class FakeProvider:
    def __init__(self, response: StrategyParseDraft | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def parse(self, *, model: str, strategy_text: str) -> StrategyParseDraft:
        self.calls.append((model, strategy_text))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def parser_for(response: StrategyParseDraft | Exception) -> OpenAIStrategyParser:
    provider = FakeProvider(response)
    return OpenAIStrategyParser(
        api_key="test-key-not-printed",
        model="test-model",
        provider_factory=lambda _: provider,
    )


def test_strict_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        StrategyParseDraft.model_validate({"entry": None, "unknown": "field"})


def test_provider_schema_avoids_unsupported_one_of() -> None:
    assert '"oneOf":' not in json.dumps(StrategyParseDraft.model_json_schema())


def test_entry_only_prompt_applies_defaults_and_infers_opposite_exit() -> None:
    parser = parser_for(StrategyParseDraft(entry=crossover(Operator.CROSSES_ABOVE)))

    result = parser.parse("Buy SPY when the 50-day SMA crosses above the 200-day SMA.")

    assert result.specification.symbol == "SPY"
    assert result.specification.interval == "1d"
    assert result.specification.exit.operator is Operator.CROSSES_BELOW
    assert result.requires_confirmation is True
    assert {item.field for item in result.defaults_applied} >= {
        "symbol",
        "interval",
        "execution.direction",
        "execution.position_size_percent",
        "execution.signal_execution",
    }
    assert any(item.field == "exit" for item in result.assumptions)


def test_exit_only_prompt_infers_opposite_entry() -> None:
    result = normalize_strategy_draft(
        StrategyParseDraft(exit=crossover(Operator.CROSSES_BELOW)),
        original_text="Sell when the 50-day SMA crosses below the 200-day SMA.",
    )

    assert result.specification.entry.operator is Operator.CROSSES_ABOVE
    assert any(item.field == "entry" for item in result.assumptions)


@pytest.mark.parametrize(
    ("strategy_text", "entry_operator", "exit_operator"),
    [
        (
            "Run a 50/200 crossover strategy.",
            Operator.CROSSES_ABOVE,
            Operator.CROSSES_BELOW,
        ),
        ("Use a golden cross strategy.", Operator.CROSSES_ABOVE, Operator.CROSSES_BELOW),
        ("Use a death cross strategy.", Operator.CROSSES_BELOW, Operator.CROSSES_ABOVE),
    ],
)
def test_recognized_shorthand_creates_confirmable_strategy(
    strategy_text: str,
    entry_operator: Operator,
    exit_operator: Operator,
) -> None:
    result = normalize_strategy_draft(StrategyParseDraft(), original_text=strategy_text)

    assert result.specification.entry.operator is entry_operator
    assert result.specification.exit.operator is exit_operator
    assert isinstance(result.specification.entry.left, IndicatorOperand)
    assert isinstance(result.specification.entry.right, IndicatorOperand)
    assert result.specification.entry.left.name is IndicatorName.SMA
    assert result.specification.entry.left.period == 50
    assert result.specification.entry.right.period == 200
    assert result.requires_confirmation is True
    assert result.assumptions


def test_unspecified_moving_average_type_becomes_confirmable_sma_assumption() -> None:
    result = normalize_strategy_draft(
        StrategyParseDraft(
            entry=crossover(Operator.CROSSES_ABOVE, short_name=None),
            exit=crossover(Operator.CROSSES_BELOW, short_name=None),
        ),
        original_text=(
            "Buy when the 50-day moving average crosses above the 200-day moving average."
        ),
    )

    assert isinstance(result.specification.entry.left, IndicatorOperand)
    assert result.specification.entry.left.name is IndicatorName.SMA
    assert any(item.field == "entry.left.name" for item in result.assumptions)
    assert result.requires_confirmation is True


def test_valid_ema_and_price_constant_conditions_normalize() -> None:
    ema_entry = ConditionDraft(
        left=OperandDraft(type="indicator", name=IndicatorName.EMA, source="close", period=20),
        operator=Operator.GREATER_THAN,
        right=OperandDraft(type="constant", value=Decimal("100")),
    )
    price_exit = ConditionDraft(
        left=OperandDraft(type="price"),
        operator=Operator.LESS_THAN,
        right=OperandDraft(type="indicator", name=IndicatorName.EMA, period=20),
    )

    result = normalize_strategy_draft(
        StrategyParseDraft(entry=ema_entry, exit=price_exit),
        original_text=(
            "Buy when the 20-day EMA is above 100. Sell when close is below the 20-day EMA."
        ),
    )

    assert isinstance(result.specification.entry.left, IndicatorOperand)
    assert result.specification.entry.left.name is IndicatorName.EMA
    assert result.specification.exit.left.type == "price"
    assert result.specification.entry.right.type == "constant"


@pytest.mark.parametrize(
    ("draft", "text", "message"),
    [
        (StrategyParseDraft(), "Buy when moving average rises.", "moving-average periods"),
        (
            StrategyParseDraft(entry=crossover(Operator.CROSSES_ABOVE, short_period=0)),
            "Buy when the 0-day SMA crosses above the 200-day SMA.",
            "positive integers",
        ),
        (
            StrategyParseDraft(entry=crossover(Operator.CROSSES_ABOVE, short_period=-1)),
            "Buy when the -1-day SMA crosses above the 200-day SMA.",
            "positive integers",
        ),
        (
            StrategyParseDraft(entry=crossover(Operator.CROSSES_ABOVE, long_period=1001)),
            "Buy when the 50-day SMA crosses above the 1001-day SMA.",
            "no greater than 1,000",
        ),
    ],
)
def test_missing_or_invalid_periods_are_rejected(
    draft: StrategyParseDraft,
    text: str,
    message: str,
) -> None:
    with pytest.raises(StrategyValidationError, match=message):
        parser_for(draft).parse(text)


@pytest.mark.parametrize(
    ("strategy_text", "message"),
    [
        ("Buy SPY when RSI is below 30.", "RSI"),
        ("Short SPY when the 50-day SMA crosses below the 200-day SMA.", "Short"),
        ("Sell at a 5% stop loss.", "Stop losses"),
        ("Buy based on positive news sentiment.", "News-based"),
        ("Buy when momentum is strong.", "Momentum"),
    ],
)
def test_unsupported_or_ambiguous_language_is_rejected_before_provider(
    strategy_text: str,
    message: str,
) -> None:
    provider = FakeProvider(StrategyParseDraft())
    parser = OpenAIStrategyParser(
        api_key="test-key-not-printed",
        model="test-model",
        provider_factory=lambda _: provider,
    )

    with pytest.raises(StrategyValidationError, match=message):
        parser.parse(strategy_text)

    assert provider.calls == []


def test_missing_key_is_raised_only_when_parser_is_invoked() -> None:
    parser = OpenAIStrategyParser(api_key=None, model="test-model")

    with pytest.raises(StrategyParserError, match="OPENAI_API_KEY") as error:
        parser.parse("Buy SPY when the 50-day SMA crosses above the 200-day SMA.")

    assert "test-key" not in str(error.value)


@pytest.mark.parametrize(
    "error",
    [
        StrategyMalformedOutputError("Malformed output."),
        StrategyProviderRefusalError("Refusal."),
        StrategyProviderTimeoutError("Timed out."),
        StrategyProviderError("Provider failed."),
    ],
)
def test_provider_errors_are_clear_and_do_not_expose_key(error: Exception) -> None:
    parser = parser_for(error)

    with pytest.raises(type(error)) as raised:
        parser.parse("Buy SPY when the 50-day SMA crosses above the 200-day SMA.")

    assert "test-key" not in str(raised.value)


def test_interpretation_and_normalized_json_are_deterministic() -> None:
    draft = StrategyParseDraft(entry=crossover(Operator.CROSSES_ABOVE))
    text = "Buy SPY when the 50-day SMA crosses above the 200-day SMA."

    first = normalize_strategy_draft(draft, original_text=text)
    second = normalize_strategy_draft(draft, original_text=text)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    interpretation = interpret_strategy(first)
    assert interpretation == interpret_strategy(second)
    assert "Platform defaults applied:" in interpretation
    assert "Assumptions made:" in interpretation
    assert "Confirmation required: Yes" in interpretation
    assert all(value is not None for value in first.specification.execution.model_dump().values())
