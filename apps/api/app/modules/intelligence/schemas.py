"""AI-owned component contracts; incident candidates reuse the backend draft type."""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field, model_validator

from app.modules.facilities.schemas import ContractModel

ComponentStatus = Literal["completed", "unavailable", "failed", "refused"]
QuestionName = Literal[
    "outage_reported",
    "multiple_facilities_reported",
    "resource_loss_reported",
    "clarification_needed",
]
Draft = TypeVar("Draft", bound=BaseModel)


class ReportRequest(ContractModel):
    report_text: str = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def nonblank(self):
        if not self.report_text.strip():
            raise ValueError("Report text must not be blank.")
        return self


class ReviewAnswer(ContractModel):
    name: QuestionName
    value: Literal["yes", "no", "unclear"] | None
    answer_status: Literal["completed", "refused"]

    @model_validator(mode="after")
    def refusal_value(self):
        if (self.answer_status == "refused") != (self.value is None):
            raise ValueError(
                "Refused answers must have null values; completed answers need choices."
            )
        return self


class AssessmentResponse(ContractModel):
    assessment_status: ComponentStatus
    answers: list[ReviewAnswer]
    model: str | None
    rubric_version: str
    elapsed_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def consistent_answers(self):
        names = [answer.name for answer in self.answers]
        expected = {
            "outage_reported",
            "multiple_facilities_reported",
            "resource_loss_reported",
            "clarification_needed",
        }
        if self.assessment_status in {"completed", "refused"}:
            if len(names) != 4 or set(names) != expected:
                raise ValueError("Assessment must contain each of the four review answers once.")
            all_refused = all(answer.answer_status == "refused" for answer in self.answers)
            if (self.assessment_status == "refused") != all_refused:
                raise ValueError("Only a fully refused assessment has component status refused.")
        elif self.answers:
            raise ValueError("Failed or unavailable assessment cannot contain successful answers.")
        return self


class Evidence(ContractModel):
    field_path: str = Field(min_length=1, max_length=200)
    source_excerpt: str = Field(min_length=1, max_length=10_000)


class ExtractionProposal(ContractModel, Generic[Draft]):
    """Provider Structured Output; specialize with IncidentDraftInput, never copy it."""

    candidate: Draft
    evidence: list[Evidence]
    questions: list[str]
    warnings: list[str]


class ExtractionResponse(ContractModel, Generic[Draft]):
    extraction_status: ComponentStatus
    candidate: Draft | None
    evidence: list[Evidence]
    questions: list[str]
    warnings: list[str]
    model: str | None
    elapsed_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def candidate_status(self):
        if (self.extraction_status == "completed") != (self.candidate is not None):
            raise ValueError("Only completed extraction can contain a candidate.")
        if self.candidate is None and self.evidence:
            raise ValueError("Failed extraction cannot contain proposal evidence.")
        return self
