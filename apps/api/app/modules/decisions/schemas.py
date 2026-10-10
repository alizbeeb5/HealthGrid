"""Shared Feature 8 decision and outcome-review contract. Owner: backend/data (the
outcome-engine owner reviews numerical fields). See docs/feature-8-contract.md.

Three dimensions stay separate: approval (a recorded human choice), reported
completion (self-reported execution) and outcome evidence (fresh hospital reports
compared with the frozen expectation). Identities are self-reported demo names, not
authenticated users. The outcome engine interface is
`evaluate_outcome(OutcomeEvaluationInput) -> OutcomeEvaluationResult`.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from app.modules.allocation.schemas import Count, FacilityExclusion
from app.modules.capacity.schemas import CapacityUnit, ServiceCapacityResult, ServiceRequirement
from app.modules.facilities.schemas import (
    ContractModel,
    DataStatus,
    FacilitySnapshotResponse,
    FieldError,
    Identifier,
)

SCHEMA_VERSION = 1
Name = Annotated[str, Field(min_length=1, max_length=100)]
Note = Annotated[str, Field(min_length=1, max_length=2000)]
IdentityMode = Literal["demo_self_reported"]


class SourceType(StrEnum):
    ALLOCATION = "allocation"
    INVESTMENT = "investment"


class DecisionStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


TERMINAL_DECISION = {DecisionStatus.COMPLETED, DecisionStatus.REJECTED, DecisionStatus.CANCELLED}


class ActionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Frozen source expectation.


class ExpectedFacility(ContractModel):
    facility_id: Identifier
    required_service_places: Count  # frozen planning assumption, not measured demand
    capacity_before: Count  # source baseline summary
    expected_capacity: Count  # source proposed summary


class SourceExpectation(ContractModel):
    """Frozen at decision creation from the saved source run; never recomputed."""

    source_type: SourceType
    source_run_id: Identifier
    source_engine_version: str
    source_created_at: AwareDatetime
    plan_outcome: Literal["improved", "no_improvement"]
    incident_id: Identifier
    revision_id: Identifier
    baseline_id: Identifier
    baseline_captured_at: AwareDatetime
    service_id: Identifier
    capacity_unit: CapacityUnit
    requirement: ServiceRequirement
    expected_at: AwareDatetime  # investment evaluation_at; allocation start + horizon
    facilities: list[ExpectedFacility]  # included facilities, by facility_id
    excluded_facilities: list[FacilityExclusion]
    expected_unmet_service_places: Count  # against planned demand
    proposed_cost_minor_units: Count  # proposal cost; never mixed with actual payments
    proposed_capital_cost_minor_units: Count | None  # investment only
    proposed_operating_cost_minor_units: Count | None  # investment only
    currency: Literal["USD"]


class ActionCorrection(ContractModel):
    corrected_at: AwareDatetime
    actor_name: Name
    reason: Note
    previous_completed_at: AwareDatetime | None
    previous_evidence_note: Note | None
    previous_actual_cost_minor_units: Count | None


class ActionItem(ContractModel):
    action_id: Identifier
    action_type: Literal["transfer", "project"]
    reference_id: Identifier  # route_id or candidate_id in the source run
    description: str = Field(min_length=1, max_length=500)
    facility_ids: list[Identifier]
    requires_action_ids: list[Identifier]
    status: ActionStatus
    proposed_cost_minor_units: Count
    proposed_ready_at: AwareDatetime | None
    reported_started_at: AwareDatetime | None
    reported_completed_at: AwareDatetime | None
    actual_cost_minor_units: Count | None  # optional; unknown is not zero
    evidence_note: Note | None
    blocker_note: Note | None
    corrections: list[ActionCorrection]


# Event commands (discriminated payloads).


class EditDraftPayload(ContractModel):
    event_type: Literal["edit_draft"]
    title: str | None = Field(min_length=1, max_length=200)
    owner_name: Name | None
    rationale: Note | None
    target_completion_at: AwareDatetime | None

    @model_validator(mode="after")
    def changes_something(self) -> Self:
        if all(v is None for v in (self.title, self.owner_name, self.rationale,
                                   self.target_completion_at)):
            raise ValueError("Change at least one draft field.")
        return self


class SubmitPayload(ContractModel):
    event_type: Literal["submit"]


class ApprovePayload(ContractModel):
    event_type: Literal["approve"]


class RejectPayload(ContractModel):
    event_type: Literal["reject"]


class StartPayload(ContractModel):
    event_type: Literal["start"]
    occurred_at: AwareDatetime


class UpdateActionPayload(ContractModel):
    event_type: Literal["update_action"]
    action_id: Identifier
    status: Literal["in_progress", "blocked", "completed"]
    occurred_at: AwareDatetime
    evidence_note: Note | None
    actual_cost_minor_units: Count | None
    blocker_note: Note | None

    @model_validator(mode="after")
    def required_details(self) -> Self:
        if self.status == "completed" and self.evidence_note is None:
            raise ValueError("Completion needs an evidence_note.")
        if self.status == "blocked" and self.blocker_note is None:
            raise ValueError("A blocked action needs a blocker_note.")
        return self


class CompletePayload(ContractModel):
    event_type: Literal["complete"]
    occurred_at: AwareDatetime


class CancelPayload(ContractModel):
    event_type: Literal["cancel"]


class CorrectActionReportPayload(ContractModel):
    event_type: Literal["correct_action_report"]
    action_id: Identifier
    reason: Note
    completed_at: AwareDatetime | None
    evidence_note: Note | None
    actual_cost_minor_units: Count | None

    @model_validator(mode="after")
    def corrects_something(self) -> Self:
        if all(v is None for v in (self.completed_at, self.evidence_note,
                                   self.actual_cost_minor_units)):
            raise ValueError("Correct at least one reported value.")
        return self


EventPayload = Annotated[
    EditDraftPayload | SubmitPayload | ApprovePayload | RejectPayload | StartPayload
    | UpdateActionPayload | CompletePayload | CancelPayload | CorrectActionReportPayload,
    Field(discriminator="event_type"),
]
EventType = Literal["edit_draft", "submit", "approve", "reject", "start", "update_action",
                    "complete", "cancel", "correct_action_report"]
NOTE_REQUIRED = {"approve", "reject", "cancel", "complete"}


class DecisionEventRequest(ContractModel):
    event_type: EventType
    expected_version: Annotated[int, Field(ge=1, strict=True)]
    request_id: Identifier  # idempotency key
    actor_name: Name
    note: Note | None
    payload: EventPayload

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.payload.event_type != self.event_type:
            raise ValueError("payload.event_type must equal event_type.")
        if self.event_type in NOTE_REQUIRED and self.note is None:
            raise ValueError(f"{self.event_type} requires an explanatory note.")
        return self


class DecisionEvent(ContractModel):
    """Append-only timeline entry. recorded_at is server time; occurred_at is the
    human-reported time, when the event has one."""

    event_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    event_type: Literal["create"] | EventType
    request_id: Identifier | None
    actor_name: Name
    identity_mode: IdentityMode
    note: Note | None
    occurred_at: AwareDatetime | None
    recorded_at: AwareDatetime
    payload: EventPayload | None
    status_after: DecisionStatus
    version_after: int


# Decisions.


class DecisionCreateRequest(ContractModel):
    source_type: SourceType
    source_run_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    owner_name: Name
    rationale: Note
    target_completion_at: AwareDatetime
    actor_name: Name
    prerequisite_decision_id: Identifier | None
    supersedes_decision_id: Identifier | None


class DecisionRecord(ContractModel):
    decision_id: Identifier
    source_type: SourceType
    source_run_id: Identifier
    incident_id: Identifier
    revision_id: Identifier
    baseline_id: Identifier
    title: str
    owner_name: Name
    rationale: Note
    target_completion_at: AwareDatetime
    status: DecisionStatus
    version: int
    identity_mode: IdentityMode
    created_at: AwareDatetime
    updated_at: AwareDatetime
    prerequisite_decision_id: Identifier | None
    supersedes_decision_id: Identifier | None
    expectation: SourceExpectation
    actions: list[ActionItem]
    events: list[DecisionEvent]


class DecisionListResponse(ContractModel):
    items: list[DecisionRecord]


# Outcome reviews and the outcome engine interface.


class OutcomeReviewRequest(ContractModel):
    actor_name: Name
    note: Note | None
    request_id: Identifier
    observation_window_starts_at: AwareDatetime


class OutcomeFacilityInput(ContractModel):
    facility_id: Identifier
    required_service_places: Count
    capacity_before: Count
    expected_capacity: Count
    snapshot: FacilitySnapshotResponse  # captured at review time; frozen


class OutcomeEvaluationInput(ContractModel):
    service_id: Identifier
    capacity_unit: CapacityUnit
    requirement: ServiceRequirement  # the source's frozen profile
    expected_at: AwareDatetime
    target_completion_at: AwareDatetime  # shown separately; never replaces expected_at
    observation_window_starts_at: AwareDatetime
    captured_at: AwareDatetime
    stale_after_hours: int
    decision_status: DecisionStatus
    facilities: list[OutcomeFacilityInput]
    excluded_facilities: list[FacilityExclusion]


class OutcomeClassification(StrEnum):
    AT_OR_ABOVE_EXPECTED = "at_or_above_expected"
    BELOW_EXPECTED = "below_expected"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    TOO_EARLY = "too_early"
    NOT_COMPARABLE = "not_comparable"


class EvidenceStatus(StrEnum):
    FRESH = "fresh"  # inside the window and fresh at capture
    OUTSIDE_WINDOW = "outside_window"
    STALE = "stale"
    MISSING = "missing"


class ResourceEvidence(ContractModel):
    resource_id: Identifier
    observation_id: Identifier | None
    available_quantity: float | None
    observed_at: AwareDatetime | None
    data_status: DataStatus  # as captured by Feature 1
    evidence_status: EvidenceStatus


class FacilityOutcome(ContractModel):
    facility_id: Identifier
    classification: OutcomeClassification
    expected_capacity: Count
    observed_capacity: Count | None  # null without comparison; unavailable is explicit zero
    capacity_difference: int | None  # observed - expected, when comparable
    observed: ServiceCapacityResult | None
    evidence: list[ResourceEvidence]
    reasons: list[str]
    unmet_against_planned_demand: Count | None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        comparable = self.classification in (OutcomeClassification.AT_OR_ABOVE_EXPECTED,
                                             OutcomeClassification.BELOW_EXPECTED)
        if comparable != (self.observed_capacity is not None):
            raise ValueError("Only comparable rows have an observed capacity.")
        if comparable:
            difference = self.observed_capacity - self.expected_capacity
            if self.capacity_difference != difference:
                raise ValueError("capacity_difference = observed - expected.")
            expected = (OutcomeClassification.AT_OR_ABOVE_EXPECTED if difference >= 0
                        else OutcomeClassification.BELOW_EXPECTED)
            if self.classification != expected:
                raise ValueError(f"classification must be {expected}.")
        elif self.capacity_difference is not None or self.unmet_against_planned_demand is not None:
            raise ValueError("Non-comparable rows have no difference or unmet demand.")
        return self


class OutcomeCoverage(ContractModel):
    comparable_facility_ids: list[Identifier]
    not_comparable_facility_ids: list[Identifier]
    excluded_facilities: list[FacilityExclusion]  # excluded by the source proposal


class OutcomeEvaluationResult(ContractModel):
    engine_version: str = Field(min_length=1, max_length=64)
    timing: Literal["too_early", "on_or_after_expected"]
    captured_offset_minutes: int  # captured_at - expected_at, signed
    facilities: list[FacilityOutcome]  # one per expected facility, by facility_id
    coverage: OutcomeCoverage
    reasons: list[str]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        ids = [f.facility_id for f in self.facilities]
        if ids != sorted(set(ids)):
            raise ValueError("facilities must be ordered by unique facility_id.")
        comparable = [f.facility_id for f in self.facilities if f.observed_capacity is not None]
        if self.coverage.comparable_facility_ids != comparable or sorted(
            self.coverage.not_comparable_facility_ids + comparable
        ) != ids:
            raise ValueError("Coverage must partition the facilities.")
        if self.timing == "too_early" and comparable:
            raise ValueError("A review before the expected date has no comparable rows.")
        return self


class OutcomeReview(OutcomeEvaluationResult):
    """Captured follow-up review. Reopening returns it; later reports create a new one."""

    review_id: Identifier
    decision_id: Identifier
    source_type: SourceType
    source_run_id: Identifier
    request_id: Identifier
    actor_name: Name
    identity_mode: IdentityMode
    note: Note | None
    captured_at: AwareDatetime
    observation_window_starts_at: AwareDatetime
    expected_at: AwareDatetime
    target_completion_at: AwareDatetime
    decision_status: DecisionStatus
    decision_version: int
    requirement: ServiceRequirement
    snapshots: list[FacilitySnapshotResponse]
    schema_version: Literal[1]


class OutcomeReviewListResponse(ContractModel):
    items: list[OutcomeReview]


# Errors.

DecisionErrorCode = Literal[
    "invalid_request", "source_run_not_found", "decision_not_found", "review_not_found",
    "invalid_transition", "prerequisite_not_met", "duplicate_source_decision",
    "version_conflict", "idempotency_conflict",
]


class DecisionErrorDetail(ContractModel):
    code: DecisionErrorCode
    message: str
    fields: list[FieldError]
    current_version: int | None  # set on version_conflict
    existing_decision_id: Identifier | None  # set on duplicate_source_decision


class DecisionErrorResponse(ContractModel):
    error: DecisionErrorDetail

