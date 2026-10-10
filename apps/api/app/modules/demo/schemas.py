from typing import Literal

from pydantic import AwareDatetime, Field

from app.modules.allocation.schemas import AllocationRunRequest
from app.modules.facilities.schemas import ContractModel, ResourceDefinition
from app.modules.investments.schemas import InvestmentRunRequest
from app.modules.scenarios.schemas import IncidentDraftInput

Phase = Literal["assessment", "response", "recovery"]


class ExerciseMetric(ContractModel):
    label: str
    covered: int
    unmet: int
    cost_minor_units: int


class ExerciseHospital(ContractModel):
    facility_id: str
    name: str
    role: str
    cause: str
    next_action: str


class ExerciseContext(ContractModel):
    enabled: bool
    title: str = "Beirut explosion exercise"
    synthetic: Literal[True] = True
    phase: Phase | None = None
    clock: AwareDatetime | None = None
    links: dict[str, str] = Field(default_factory=dict)
    hospitals: list[ExerciseHospital] = Field(default_factory=list)
    resources: list[ResourceDefinition] = Field(default_factory=list)
    metrics: list[ExerciseMetric] = Field(default_factory=list)
    incident_input: IncidentDraftInput | None = None
    allocation_input: AllocationRunRequest | None = None
    investment_input: InvestmentRunRequest | None = None
    allocation_decision_id: str | None = None
    investment_decision_id: str | None = None
    missing_review_id: str | None = None
    supported_review_id: str | None = None


class AdvanceExercise(ContractModel):
    expected_phase: Phase
    target_phase: Literal["response", "recovery"]
