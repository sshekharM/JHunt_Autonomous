"""Request/response models for /api/consent (CHG-007)."""
from datetime import datetime
from typing import Literal

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


class DeletionSummary(BaseModel):
    """What execute_deletion reports for the soft delete a data_processing withdrawal starts."""
    mode: str
    message: str
    hard_delete_after: str | None = None


class WithdrawConsentResponse(BaseModel):
    withdrawn: list[str]
    current: ConsentFlags
    account_deletion: DeletionSummary | None
