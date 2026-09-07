from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OperationsAgentRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class ToolExecution(BaseModel):
    tool: str
    label: str
    result_count: int


class ActionProposalResponse(BaseModel):
    id: int
    ai_run_id: int
    action_type: str
    action_payload: dict
    status: str
    created_by: int
    reviewed_by: int | None
    review_notes: str | None
    reviewed_at: datetime | None
    executed_entity_type: str | None
    executed_entity_id: int | None
    created_at: datetime
    updated_at: datetime


class ActionProposalReview(BaseModel):
    decision: Literal["approved", "rejected"]
    notes: str | None = Field(default=None, max_length=1000)


class OperationsAgentResponse(BaseModel):
    run_id: int
    answer: str
    tools_used: list[ToolExecution]
    node_trace: list[str]
    guardrails: dict
    provider: str
    fallback_used: bool
    proposed_actions: list[ActionProposalResponse] = Field(default_factory=list)
