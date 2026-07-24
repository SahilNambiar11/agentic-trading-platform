from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast

from app.core.config import Environment, get_settings
from app.schemas.strategy_spec import (
    AppliedDefault,
    AssumptionConfidence,
    Condition,
    ConditionDraft,
    ConstantOperand,
    ExecutionSettings,
    IndicatorName,
    IndicatorOperand,
    Operand,
    OperandDraft,
    Operator,
    ParsedStrategyResult,
    PriceOperand,
    StrategyAssumption,
    StrategyParseDraft,
    StrategySpecification,
)
from app.services.strategy_semantics import (
    StrategyValidationError,
    find_normalization_hint,
    validate_strategy_semantics,
    validate_strategy_text,
)


class StrategyParserError(RuntimeError):
    """Base parser error that never includes provider credentials."""


class StrategyProviderError(StrategyParserError):
    pass


class StrategyProviderRefusalError(StrategyProviderError):
    pass


class StrategyProviderTimeoutError(StrategyProviderError):
    pass


class StrategyMalformedOutputError(StrategyProviderError):
    pass


class StructuredStrategyProvider(Protocol):
    def parse(self, *, model: str, strategy_text: str) -> StrategyParseDraft: ...


class StrategyParser(Protocol):
    def parse(self, strategy_text: str) -> ParsedStrategyResult: ...


class OpenAIResponsesProvider:
    """OpenAI Structured Outputs adapter, instantiated only on parser use."""

    def __init__(self, api_key: str) -> None:
        try:
            from openai import OpenAI
        except ImportError as error:
            raise StrategyProviderError("OpenAI SDK is not installed.") from error

        self._client = OpenAI(api_key=api_key)

    def parse(self, *, model: str, strategy_text: str) -> StrategyParseDraft:
        try:
            response = self._client.responses.parse(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Translate only the user's strategy into the supplied strict schema. "
                            "Do not write code, SQL, explanations, or market-data analysis. "
                            "Leave omitted fields null in the draft rather than inventing values. "
                            "Recognize only close price, SMA, EMA, numeric constants, and the "
                            "supported comparison/crossover operators."
                        ),
                    },
                    {"role": "user", "content": strategy_text},
                ],
                text_format=StrategyParseDraft,
            )
        except TimeoutError as error:
            raise StrategyProviderTimeoutError(
                "The strategy parser timed out. Please try again."
            ) from error
        except Exception as error:
            if error.__class__.__name__ == "APITimeoutError":
                raise StrategyProviderTimeoutError(
                    "The strategy parser timed out. Please try again."
                ) from error
            raise StrategyProviderError(provider_error_message(error)) from error

        parsed = response.output_parsed
        if parsed is not None:
            return parsed
        if response_contains_refusal(cast(dict[str, object], response.model_dump(mode="python"))):
            raise StrategyProviderRefusalError("The strategy parser refused this request.")
        raise StrategyMalformedOutputError(
            "The strategy parser returned malformed structured output."
        )


def response_contains_refusal(response: dict[str, object]) -> bool:
    output = response.get("output")
    if not isinstance(output, list):
        return False
    for item in cast(list[object], output):
        if not isinstance(item, dict):
            continue
        content = cast(dict[str, object], item).get("content")
        if not isinstance(content, list):
            continue
        if any(
            isinstance(part, dict) and cast(dict[str, object], part).get("type") == "refusal"
            for part in cast(list[object], content)
        ):
            return True
    return False


def provider_error_message(error: Exception) -> str:
    if get_settings().environment is Environment.LOCAL:
        return f"The strategy parser provider returned {type(error).__name__}: {error}"
    return "The strategy parser provider returned an error."


class OpenAIStrategyParser:
    """Provider-independent parser entry point with deterministic normalization."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        provider_factory: Callable[[str], StructuredStrategyProvider] = OpenAIResponsesProvider,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._provider_factory = provider_factory

    @classmethod
    def from_settings(cls) -> OpenAIStrategyParser:
        settings = get_settings()
        api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        return cls(api_key=api_key, model=settings.openai_model)

    def parse(self, strategy_text: str) -> ParsedStrategyResult:
        if not strategy_text.strip():
            raise StrategyValidationError("Enter a strategy description.")
        validate_strategy_text(strategy_text)
        if not self._api_key:
            raise StrategyParserError("OPENAI_API_KEY is required to parse a strategy.")
        if not self._model:
            raise StrategyParserError("OPENAI_MODEL is required to parse a strategy.")

        draft = self._provider_factory(self._api_key).parse(
            model=self._model,
            strategy_text=strategy_text,
        )
        return normalize_strategy_draft(draft, original_text=strategy_text)


def normalize_strategy_draft(
    draft: StrategyParseDraft,
    *,
    original_text: str,
) -> ParsedStrategyResult:
    """Apply fixed defaults and the small, user-visible assumption set."""

    assumptions: list[StrategyAssumption] = []
    defaults: list[AppliedDefault] = []
    symbol = draft.symbol
    if symbol is None:
        symbol = "SPY"
        apply_default(defaults, "symbol", symbol, "SPY is the only supported symbol.")
    interval = draft.interval
    if interval is None:
        interval = "1d"
        apply_default(defaults, "interval", interval, "Daily bars are fixed in version 1.")
    direction = draft.direction
    if direction is None:
        direction = "long"
        apply_default(
            defaults,
            "execution.direction",
            direction,
            "Long-only execution is fixed in version 1.",
        )
    position_size = draft.position_size_percent
    if position_size is None:
        position_size = 100
        apply_default(
            defaults,
            "execution.position_size_percent",
            position_size,
            "Position sizing is fixed at 100% of available cash in version 1.",
        )
    signal_execution = draft.signal_execution
    if signal_execution is None:
        signal_execution = "next_bar_open"
        apply_default(
            defaults,
            "execution.signal_execution",
            signal_execution,
            "Signals execute at the next available trading bar open in version 1.",
        )

    entry_draft = draft.entry
    exit_draft = draft.exit
    if entry_draft is None and exit_draft is None:
        entry_draft, exit_draft = infer_shorthand_pair(original_text, assumptions)

    if entry_draft is None and exit_draft is not None:
        entry_draft = opposite_crossover_draft(exit_draft)
        assumptions.append(
            assumption(
                "entry",
                entry_draft.model_dump(mode="json"),
                "No entry rule was provided, so the opposite crossover was used as the entry.",
            )
        )
    if exit_draft is None and entry_draft is not None:
        exit_draft = opposite_crossover_draft(entry_draft)
        assumptions.append(
            assumption(
                "exit",
                exit_draft.model_dump(mode="json"),
                "No exit rule was provided, so the opposite crossover was used as the exit.",
            )
        )
    if entry_draft is None or exit_draft is None:
        raise StrategyValidationError(
            "Specify an entry and exit rule, or use a supported crossover shorthand."
        )

    specification = StrategySpecification(
        symbol=symbol,
        interval=interval,
        entry=normalize_condition(entry_draft, "entry", defaults, assumptions),
        exit=normalize_condition(exit_draft, "exit", defaults, assumptions),
        execution=ExecutionSettings(
            direction=direction,
            position_size_percent=position_size,
            signal_execution=signal_execution,
        ),
    )
    validate_strategy_semantics(specification)
    return ParsedStrategyResult(
        specification=specification,
        assumptions=assumptions,
        defaults_applied=defaults,
        requires_confirmation=bool(assumptions),
        original_text=original_text,
    )


def apply_default(
    defaults: list[AppliedDefault],
    field: str,
    value: str | int,
    reason: str,
) -> None:
    defaults.append(AppliedDefault(field=field, value=value, reason=reason))


def assumption(
    field: str,
    inferred_value: str | int | bool | dict[str, object] | list[object],
    reason: str,
) -> StrategyAssumption:
    return StrategyAssumption(
        field=field,
        inferred_value=inferred_value,
        reason=reason,
        confidence=AssumptionConfidence.HIGH,
    )


def infer_shorthand_pair(
    strategy_text: str,
    assumptions: list[StrategyAssumption],
) -> tuple[ConditionDraft | None, ConditionDraft | None]:
    hint = find_normalization_hint(strategy_text)
    if hint is None:
        return None, None

    bullish = crossover_draft(hint.short_period, hint.long_period, Operator.CROSSES_ABOVE)
    bearish = crossover_draft(hint.short_period, hint.long_period, Operator.CROSSES_BELOW)
    entry, exit = (bullish, bearish) if hint.bullish_entry else (bearish, bullish)
    assumptions.append(
        assumption(
            "entry_and_exit",
            {"entry": entry.model_dump(mode="json"), "exit": exit.model_dump(mode="json")},
            f"The {hint.name} was interpreted as {hint.short_period}-day SMA and "
            f"{hint.long_period}-day SMA crossover rules.",
        )
    )
    return entry, exit


def crossover_draft(short_period: int, long_period: int, operator: Operator) -> ConditionDraft:
    return ConditionDraft(
        left=OperandDraft(type="indicator", period=short_period),
        operator=operator,
        right=OperandDraft(type="indicator", period=long_period),
    )


def opposite_crossover_draft(condition: ConditionDraft) -> ConditionDraft:
    opposites = {
        Operator.CROSSES_ABOVE: Operator.CROSSES_BELOW,
        Operator.CROSSES_BELOW: Operator.CROSSES_ABOVE,
    }
    operator = condition.operator
    if operator is None or operator not in opposites:
        raise StrategyValidationError(
            "An omitted rule can be inferred only from a supported crossover condition."
        )
    return ConditionDraft(
        left=condition.left,
        operator=opposites[operator],
        right=condition.right,
    )


def normalize_condition(
    condition: ConditionDraft,
    field_name: str,
    defaults: list[AppliedDefault],
    assumptions: list[StrategyAssumption],
) -> Condition:
    if condition.operator is None:
        raise StrategyValidationError(f"Specify the comparison operator for the {field_name} rule.")
    return Condition(
        left=normalize_operand(condition.left, f"{field_name}.left", defaults, assumptions),
        operator=condition.operator,
        right=normalize_operand(condition.right, f"{field_name}.right", defaults, assumptions),
    )


def normalize_operand(
    operand: OperandDraft,
    field_name: str,
    defaults: list[AppliedDefault],
    assumptions: list[StrategyAssumption],
) -> Operand:
    if operand.type == "indicator":
        if operand.period is None:
            raise StrategyValidationError(f"Specify the moving-average period for {field_name}.")
        name = operand.name
        if name is None:
            name = IndicatorName.SMA
            assumptions.append(
                assumption(
                    f"{field_name}.name",
                    "sma",
                    f"Unspecified moving-average type for {field_name} was interpreted as SMA.",
                )
            )
        source = operand.source
        if source is None:
            source = "close"
            apply_default(
                defaults,
                f"{field_name}.source",
                source,
                "Raw close price is the fixed source in version 1.",
            )
        return IndicatorOperand(type="indicator", name=name, source=source, period=operand.period)
    if operand.type == "price":
        source = operand.source
        if source is None:
            source = "close"
            apply_default(
                defaults,
                f"{field_name}.source",
                source,
                "Raw close price is the fixed source in version 1.",
            )
        return PriceOperand(type="price", source=source)
    if operand.value is None:
        raise StrategyValidationError(f"Specify the numeric constant for {field_name}.")
    return ConstantOperand(type="constant", value=operand.value)
