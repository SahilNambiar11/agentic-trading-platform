from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, StringConstraints, model_validator

from app.schemas.strategy_spec import (
    AppliedDefault,
    ParsedStrategyResult,
    StrategyAssumption,
    StrategySpecification,
)

StrategyName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
StrategySourceText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
StrategyJson = dict[str, JsonValue]


class StrategyRequest(BaseModel):
    """Base request model that rejects unexpected client-supplied fields."""

    model_config = ConfigDict(extra="forbid")


class StrategyCreate(StrategyRequest):
    """Payload accepted when a user creates a saved strategy."""

    name: StrategyName
    source_text: StrategySourceText
    strategy_json: StrategyJson | None = None


class StrategyUpdate(StrategyRequest):
    """Payload accepted when a user edits an existing strategy."""

    name: StrategyName | None = None
    source_text: StrategySourceText | None = None
    strategy_json: StrategyJson | None = None

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> Self:
        """Prevent PATCH requests from setting required DB columns to null."""
        for field_name in ("name", "source_text"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class StrategyResponse(BaseModel):
    """Public API representation of a strategy row.

    Notice that `user_id` is intentionally omitted. The owner is enforced by the
    backend and database, but the browser does not need to receive it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    source_text: str
    strategy_json: StrategyJson | None
    created_at: datetime
    updated_at: datetime


class StrategyPreviewRequest(StrategyRequest):
    text: StrategySourceText


class ParsedStrategyReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specification: StrategySpecification
    defaults_applied: list[AppliedDefault]
    assumptions: list[StrategyAssumption]
    requires_confirmation: bool
    original_text: str
    interpretation: str

    @classmethod
    def from_parsed_result(
        cls, result: ParsedStrategyResult, interpretation: str
    ) -> "ParsedStrategyReview":
        return cls(
            specification=result.specification,
            defaults_applied=result.defaults_applied,
            assumptions=result.assumptions,
            requires_confirmation=result.requires_confirmation,
            original_text=result.original_text,
            interpretation=interpretation,
        )


class BacktestPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    interval: str
    start_date: datetime
    end_date: datetime
    bar_count: int
    starting_cash: Decimal
    ending_value: Decimal
    total_return_percent: Decimal
    cagr_percent: Decimal | None
    max_drawdown_percent: Decimal
    trade_count: int
    win_rate_percent: Decimal
    buy_and_hold_return_percent: Decimal


class StrategyPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parsed_strategy: ParsedStrategyReview
    backtest: BacktestPreviewResponse


class ConfirmedStrategySaveRequest(StrategyRequest):
    name: StrategyName
    source_text: StrategySourceText
    specification: StrategySpecification
    defaults_applied: list[AppliedDefault]
    assumptions: list[StrategyAssumption]
    requires_confirmation: bool
    confirmed: bool

    @model_validator(mode="after")
    def validate_confirmation_metadata(self) -> Self:
        if not self.confirmed:
            raise ValueError("Explicit confirmation is required before saving a strategy.")
        if self.requires_confirmation != bool(self.assumptions):
            raise ValueError("Confirmation metadata does not match the strategy assumptions.")
        if any(not assumption.requires_confirmation for assumption in self.assumptions):
            raise ValueError("All recorded assumptions must require confirmation.")
        return self
