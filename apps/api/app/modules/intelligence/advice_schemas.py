"""Scenario emergency guidance: suggestions only, never a dispatch or saved simulation."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from app.modules.facilities.schemas import ContractModel, Identifier
from app.modules.intelligence.schemas import ComponentStatus, ReportRequest
from app.modules.scenarios.schemas import IncidentDraftInput

AdviceText = Annotated[str, Field(min_length=1, max_length=1200)]


class EmergencyAdviceRequest(ContractModel):
    incident: IncidentDraftInput

    @model_validator(mode="after")
    def has_report(self):
        ReportRequest(report_text=self.incident.report_text or "")
        return self


class EmergencyAction(ContractModel):
    priority: Literal["immediate", "next"]
    title: AdviceText
    facility_ids: list[Identifier] = Field(max_length=10)
    steps: list[AdviceText] = Field(min_length=1, max_length=4)
    rationale: AdviceText
    prerequisites: list[AdviceText] = Field(min_length=1, max_length=6)
    evidence_paths: list[AdviceText] = Field(min_length=1, max_length=8)


class EmergencyAdviceProposal(ContractModel):
    summary: AdviceText
    actions: list[EmergencyAction] = Field(min_length=1, max_length=5)
    questions: list[AdviceText] = Field(max_length=8)


class AdviceEvidence(ContractModel):
    path: str
    value: str | int | float | bool | None


class EmergencyAdviceResponse(ContractModel):
    advice_status: ComponentStatus
    proposal: EmergencyAdviceProposal | None
    evidence: list[AdviceEvidence]
    warnings: list[str]
    model: str | None
    elapsed_ms: int = Field(ge=0)
    as_of: AwareDatetime

    @model_validator(mode="after")
    def consistent(self):
        if (self.advice_status == "completed") != (self.proposal is not None):
            raise ValueError("Only completed guidance can contain a proposal.")
        if self.proposal is None and self.evidence:
            raise ValueError("Failed guidance cannot contain evidence.")
        return self
