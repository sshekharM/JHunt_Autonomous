"""Request/response models for /api/consent (CHG-007)."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ConsentScope = Literal["auto_apply", "llm_processing", "data_processing"]


class WithdrawConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scopes: list[ConsentScope] = Field(min_length=1)


class ConsentFlags(BaseModel):
    auto_apply: bool
    llm_processing: bool
    data_processing: bool


class ConsentEntry(BaseModel):
    event: str
    flags: ConsentFlags
    at: datetime


class ConsentView(BaseModel):
    current: ConsentFlags | None
    history: list[ConsentEntry]


class WithdrawConsentResponse(BaseModel):
    withdrawn: list[str]
    current: ConsentFlags
    account_deletion: dict[str, Any] | None
