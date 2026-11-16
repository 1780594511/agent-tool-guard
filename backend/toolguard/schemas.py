"""Strict, bounded schemas: model output never supplies an identity or an executor."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]
Classification = Literal["public", "rd", "hr"]
ToolName = Literal["read_document", "create_ticket", "export_report"]
Destination = Literal["inbox://compliance", "inbox://security"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReadDocument(StrictModel):
    document_id: Identifier


class CreateTicket(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    body: Annotated[str, Field(min_length=1, max_length=2000)]

    @field_validator("title", "body")
    @classmethod
    def meaningful(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty text")
        return value.strip()


class ExportReport(StrictModel):
    document_ids: Annotated[list[Identifier], Field(min_length=1, max_length=10)]
    destination: Annotated[str, Field(min_length=1, max_length=120)]

    @field_validator("document_ids")
    @classmethod
    def canonical_set(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


TOOL_SCHEMAS = {"read_document": ReadDocument, "create_ticket": CreateTicket, "export_report": ExportReport}


class RoleRule(StrictModel):
    tools: list[ToolName]
    classifications: list[Classification]


class Limits(StrictModel):
    max_steps: Annotated[int, Field(ge=1, le=12)] = 6
    task_timeout_seconds: Annotated[int, Field(ge=2, le=120)] = 60
    max_retries: Annotated[int, Field(ge=0, le=2)] = 1
    approval_ttl_seconds: Annotated[int, Field(ge=10, le=3600)] = 300


class Policy(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    roles: dict[str, RoleRule]
    destinations: list[Destination]
    approval_required: list[Literal["export_report"]]
    limits: Limits

    @model_validator(mode="after")
    def invariants(self):
        if set(self.roles) != {"employee", "engineer", "hr"}:
            raise ValueError("exactly three business roles required")
        if self.approval_required != ["export_report"]:
            raise ValueError("exports must always require approval")
        if len(self.destinations) != len(set(self.destinations)):
            raise ValueError("duplicate destination")
        return self


class Login(StrictModel):
    username: Identifier
    password: Annotated[str, Field(min_length=1, max_length=200)]


class ToolRequest(StrictModel):
    tool: Annotated[str, Field(min_length=1, max_length=80)]
    arguments: dict
    idempotency_key: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_:-]{1,100}$")]
    task_id: Identifier | None = None
    approval_id: Identifier | None = None

    @field_validator("arguments")
    @classmethod
    def finite_json_arguments(cls, value: dict) -> dict:
        try:
            json.dumps(value, allow_nan=False)
        except (ValueError, TypeError, RecursionError) as exc:
            raise ValueError("arguments must be finite JSON data") from exc
        return value


class TaskRequest(StrictModel):
    prompt: Annotated[str, Field(min_length=1, max_length=4000)]
    provider: Literal["mock", "openai"] = "mock"
    request_key: Identifier


class ApprovalAction(StrictModel):
    action: Literal["approve", "reject", "revoke"]


class PolicyUpdate(StrictModel):
    expected_version: Identifier
    policy: Policy


class AccessUpdate(StrictModel):
    user_id: Identifier
    document_id: Identifier
    granted: bool


class EvaluationRequest(StrictModel):
    split: Literal["dev", "holdout"] = "dev"
    repeats: Annotated[int, Field(ge=1, le=3)] = 1
    provider: Literal["mock"] = "mock"  # Real, paid experiments are an explicit local CLI operation.
