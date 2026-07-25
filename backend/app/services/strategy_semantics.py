import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.schemas.strategy_spec import (
    MAX_RISK_PERCENT,
    Condition,
    IndicatorName,
    IndicatorOperand,
    Operand,
    Operator,
    PriceOperand,
    StrategySpecification,
)


class StrategyValidationError(ValueError):
    """A clear error raised for unsupported or ambiguous strategy requests."""


UNSUPPORTED_LANGUAGE = {
    "rsi": "RSI is not supported in version 1.",
    "macd": "MACD is not supported in version 1.",
    "bollinger": "Bollinger Bands are not supported in version 1.",
    "volume": "Volume rules and volume indicators are not supported in version 1.",
    "trailing stop": "Trailing stops are not supported in version 1.",
    "short ": "Short selling is not supported in version 1.",
    "leverage": "Leverage is not supported in version 1.",
    "option": "Options are not supported in version 1.",
    "news": "News-based rules are not supported in version 1.",
    "sentiment": "Sentiment-based rules are not supported in version 1.",
    "fundamental": "Fundamental-based rules are not supported in version 1.",
    "earnings": "Earnings-based rules are not supported in version 1.",
    "analyst": "Analyst-rating rules are not supported in version 1.",
    "python code": "Code generation is not supported for strategies.",
    "sql query": "SQL generation is not supported for strategies.",
    "select *": "SQL generation is not supported for strategies.",
}
AMBIGUOUS_LANGUAGE = {
    "looks strong": (
        "Specify a supported price or moving-average condition instead of 'looks strong'."
    ),
    "momentum": (
        "Momentum is undefined here. Specify a supported price or moving-average condition."
    ),
    "risk increases": (
        "Risk is undefined here. Specify a supported price or moving-average condition."
    ),
    "conditions are favorable": "Specify a supported price or moving-average condition.",
    "good moving average": "Specify explicit moving-average periods.",
    "tight stop": "Specify an explicit stop-loss percentage.",
    "take profit when appropriate": "Specify an explicit take-profit percentage.",
    "control my downside": "Specify an explicit stop-loss percentage.",
    "good risk management": ("Specify an explicit stop-loss or take-profit percentage."),
}

PERCENT_VALUE = r"(?P<value>[+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(?:%|percent\b)"
STOP_LOSS_PATTERNS = (
    re.compile(rf"{PERCENT_VALUE}\s+stop[- ]loss\b", re.IGNORECASE),
    re.compile(
        rf"\bstop[- ]loss(?:\s+(?:of|at))?\s+{PERCENT_VALUE}",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:the\s+)?position\s+los(?:e|es|ing)\s+{PERCENT_VALUE}",
        re.IGNORECASE,
    ),
)
TAKE_PROFIT_PATTERNS = (
    re.compile(rf"{PERCENT_VALUE}\s+take[- ]profit\b", re.IGNORECASE),
    re.compile(
        rf"\btake[- ]profit(?:\s+(?:of|at))?\s+{PERCENT_VALUE}",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bgain(?:s|ing)?\s+{PERCENT_VALUE}",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class RiskControls:
    stop_loss_percent: Decimal | None
    take_profit_percent: Decimal | None


def validate_strategy_text(strategy_text: str) -> None:
    """Reject only concepts that cannot be safely normalized in version 1."""

    normalized_text = strategy_text.lower()
    for phrase, message in UNSUPPORTED_LANGUAGE.items():
        if phrase in normalized_text:
            raise StrategyValidationError(message)
    for phrase, message in AMBIGUOUS_LANGUAGE.items():
        if phrase in normalized_text:
            raise StrategyValidationError(message)
    extract_risk_controls(strategy_text)

    if "moving average" in normalized_text and not has_resolvable_moving_average(normalized_text):
        raise StrategyValidationError(
            "Specify moving-average periods, such as '50-day SMA' or '50/200 crossover'."
        )


def has_resolvable_moving_average(strategy_text: str) -> bool:
    return bool(
        re.search(r"\b\d+\s*(?:-?day\b|/)\s*\d*", strategy_text)
        or "golden cross" in strategy_text
        or "death cross" in strategy_text
    )


def validate_strategy_semantics(specification: StrategySpecification) -> None:
    """Validate deterministic-execution constraints beyond Pydantic shape checks."""

    if specification.symbol != "SPY":
        raise StrategyValidationError("Only SPY is supported in version 1.")
    if specification.interval != "1d":
        raise StrategyValidationError("Only daily (1d) bars are supported in version 1.")
    if specification.execution.direction != "long":
        raise StrategyValidationError("Only long-only strategies are supported in version 1.")
    if specification.execution.position_size_percent != 100:
        raise StrategyValidationError("Position size must be exactly 100% in version 1.")
    if specification.execution.signal_execution != "next_bar_open":
        raise StrategyValidationError("Signals must execute at the next available bar open.")

    validate_condition(specification.entry, "entry")
    validate_condition(specification.exit, "exit")
    validate_risk_percent(specification.stop_loss_percent, "Stop-loss")
    validate_risk_percent(specification.take_profit_percent, "Take-profit")


def extract_risk_controls(strategy_text: str) -> RiskControls:
    """Extract only explicit percentage risk controls from the user's text."""

    stop_loss = extract_control_percent(
        strategy_text,
        patterns=STOP_LOSS_PATTERNS,
        phrase_pattern=(r"\bstop[- ]loss\b|\bposition\s+los(?:e|es|ing)\b|\btight\s+stop\b"),
        label="Stop-loss",
    )
    take_profit = extract_control_percent(
        strategy_text,
        patterns=TAKE_PROFIT_PATTERNS,
        phrase_pattern=r"\btake[- ]profit\b|\bgain(?:s|ing)?\b",
        label="Take-profit",
    )
    return RiskControls(
        stop_loss_percent=stop_loss,
        take_profit_percent=take_profit,
    )


def extract_control_percent(
    strategy_text: str,
    *,
    patterns: tuple[re.Pattern[str], ...],
    phrase_pattern: str,
    label: str,
) -> Decimal | None:
    values: set[Decimal] = set()
    for pattern in patterns:
        for match in pattern.finditer(strategy_text):
            try:
                values.add(Decimal(match.group("value")))
            except InvalidOperation as error:
                raise StrategyValidationError(f"{label} must be an explicit percentage.") from error

    if len(values) > 1:
        rendered = ", ".join(f"{value}%" for value in sorted(values))
        raise StrategyValidationError(
            f"Conflicting {label.lower()} percentages were provided: {rendered}."
        )
    if values:
        value = next(iter(values))
        validate_risk_percent(value, label)
        return value

    if re.search(phrase_pattern, strategy_text, re.IGNORECASE):
        raise StrategyValidationError(
            f"{label} must be an explicit percentage greater than 0% "
            f"and no greater than {MAX_RISK_PERCENT}%."
        )
    return None


def validate_risk_percent(value: Decimal | None, label: str) -> None:
    if value is None:
        return
    if not value.is_finite() or value <= 0 or value > MAX_RISK_PERCENT:
        raise StrategyValidationError(
            f"{label} must be greater than 0% and no greater than {MAX_RISK_PERCENT}%."
        )


def validate_condition(condition: Condition, field_name: str) -> None:
    if condition.operator not in set(Operator):
        raise StrategyValidationError(f"Unsupported {field_name} operator.")
    validate_operand(condition.left, field_name)
    validate_operand(condition.right, field_name)


def validate_operand(operand: Operand, field_name: str) -> None:
    if isinstance(operand, IndicatorOperand):
        if operand.name not in set(IndicatorName):
            raise StrategyValidationError(f"Unsupported {field_name} indicator.")
        if operand.source != "close":
            raise StrategyValidationError("Only raw close price is currently supported.")
        if not 1 <= operand.period <= 1000:
            raise StrategyValidationError(
                "Indicator periods must be positive integers no greater than 1,000."
            )
    elif isinstance(operand, PriceOperand):
        if operand.source != "close":
            raise StrategyValidationError("Only raw close price is currently supported.")


@dataclass(frozen=True)
class NormalizationHint:
    name: str
    short_period: int
    long_period: int
    bullish_entry: bool


def find_normalization_hint(strategy_text: str) -> NormalizationHint | None:
    normalized_text = strategy_text.lower()
    if "golden cross" in normalized_text:
        return NormalizationHint("golden cross", 50, 200, True)
    if "death cross" in normalized_text:
        return NormalizationHint("death cross", 50, 200, False)

    shorthand = re.search(r"\b(\d+)\s*/\s*(\d+)\s*(?:day\s*)?crossover\b", normalized_text)
    if shorthand:
        return NormalizationHint(
            "crossover shorthand",
            int(shorthand.group(1)),
            int(shorthand.group(2)),
            True,
        )
    return None
