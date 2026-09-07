from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    expires_at: datetime
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

    @model_validator(mode="after")
    def require_rejection_notes(self):
        if self.decision == "rejected" and not (self.notes or "").strip():
            raise ValueError("退回提案時必須填寫理由")
        if self.notes is not None:
            self.notes = self.notes.strip() or None
        return self


class OperationsAgentResponse(BaseModel):
    run_id: int
    answer: str
    tools_used: list[ToolExecution]
    node_trace: list[str]
    guardrails: dict
    provider: str
    fallback_used: bool
    proposed_actions: list[ActionProposalResponse] = Field(default_factory=list)
