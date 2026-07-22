from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, StringConstraints, model_validator

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
    model_config = ConfigDict(extra="forbid")


class StrategyCreate(StrategyRequest):
    name: StrategyName
    source_text: StrategySourceText
    strategy_json: StrategyJson | None = None


class StrategyUpdate(StrategyRequest):
    name: StrategyName | None = None
    source_text: StrategySourceText | None = None
    strategy_json: StrategyJson | None = None

    @model_validator(mode="after")
    def reject_null_for_required_columns(self) -> Self:
        for field_name in ("name", "source_text"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    source_text: str
    strategy_json: StrategyJson | None
    created_at: datetime
    updated_at: datetime
