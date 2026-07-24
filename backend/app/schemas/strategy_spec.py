from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IndicatorName(StrEnum):
    SMA = "sma"
    EMA = "ema"


class Operator(StrEnum):
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"


class IndicatorOperand(StrictSchema):
    type: Literal["indicator"]
    name: IndicatorName
    source: Literal["close"]
    period: StrictInt


class PriceOperand(StrictSchema):
    type: Literal["price"]
    source: Literal["close"]


class ConstantOperand(StrictSchema):
    type: Literal["constant"]
    value: Decimal


Operand = Annotated[
    IndicatorOperand | PriceOperand | ConstantOperand,
    Field(discriminator="type"),
]


class Condition(StrictSchema):
    left: Operand
    operator: Operator
    right: Operand


class ExecutionSettings(StrictSchema):
    direction: Literal["long"]
    position_size_percent: Literal[100]
    signal_execution: Literal["next_bar_open"]


class StrategySpecification(StrictSchema):
    version: Literal["1.0"] = "1.0"
    symbol: Literal["SPY"]
    interval: Literal["1d"]
    entry: Condition
    exit: Condition
    execution: ExecutionSettings


class OperandDraft(StrictSchema):
    """Flat provider output that avoids Structured Outputs' unsupported ``oneOf``."""

    type: Literal["indicator", "price", "constant"]
    name: IndicatorName | None = None
    source: Literal["close"] | None = None
    period: StrictInt | None = None
    value: Decimal | None = None


class ConditionDraft(StrictSchema):
    left: OperandDraft
    operator: Operator | None = None
    right: OperandDraft


class StrategyParseDraft(StrictSchema):
    """Strict provider output before deterministic defaults are applied."""

    symbol: Literal["SPY"] | None = None
    interval: Literal["1d"] | None = None
    entry: ConditionDraft | None = None
    exit: ConditionDraft | None = None
    direction: Literal["long"] | None = None
    position_size_percent: Literal[100] | None = None
    signal_execution: Literal["next_bar_open"] | None = None


class AssumptionConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class StrategyAssumption(StrictSchema):
    field: str
    inferred_value: str | int | Decimal | bool | dict[str, object] | list[object]
    reason: str
    confidence: AssumptionConfidence
    requires_confirmation: Literal[True] = True


class AppliedDefault(StrictSchema):
    field: str
    value: str | int | Decimal | bool | dict[str, object] | list[object]
    reason: str


class ParsedStrategyResult(StrictSchema):
    specification: StrategySpecification
    assumptions: list[StrategyAssumption]
    defaults_applied: list[AppliedDefault]
    requires_confirmation: bool
    original_text: str
