"""Load the synthetic Feature 1 fixtures into the database. Safe to rerun.

Facilities and the resource catalog come from `contracts/examples/feature-1/`;
services, applicability and baseline observations from `data/synthetic/feature-1/`
(see its README). Rerunning never modifies or deletes existing observations.
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.facilities.models import (
    Facility,
    FacilityResource,
    FacilityService,
    ResourceDefinition,
    ResourceObservation,
    Service,
)
from app.modules.facilities.schemas import (
    FacilityListResponse,
    ObservationResponse,
)
from app.modules.facilities.schemas import (
    FacilityService as FacilityServiceContract,
)
from app.modules.facilities.schemas import (
    ResourceDefinition as ResourceDefinitionContract,
)

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "contracts" / "examples" / "feature-1"
SEED_DATA = ROOT / "data" / "synthetic" / "feature-1"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_feature_1_examples(
    db: Session, fixtures: Path = FIXTURES, seed_data: Path = SEED_DATA
) -> None:
    for row in _read(fixtures / "resource-definitions.json"):
        definition = ResourceDefinitionContract.model_validate(row)
        db.merge(ResourceDefinition(**definition.model_dump()))

    facilities = FacilityListResponse.model_validate(_read(fixtures / "facilities.response.json"))
    for facility in facilities.items:
        db.merge(Facility(**facility.model_dump(exclude={"last_reported_at"})))

    for row in _read(seed_data / "services.json"):
        service = FacilityServiceContract.model_validate(row)
        db.merge(Service(service_id=service.service_id, name=service.name))
        db.merge(
            FacilityService(
                facility_id=service.facility_id,
                service_id=service.service_id,
                status=service.status,
            )
        )

    for row in _read(seed_data / "facility-resources.json"):
        db.merge(FacilityResource(facility_id=row["facility_id"], resource_id=row["resource_id"]))
    db.flush()

    for row in _read(seed_data / "observations.json"):
        observation = ObservationResponse.model_validate(row)
        if db.get(ResourceObservation, observation.observation_id) is None:
            db.add(ResourceObservation(**observation.model_dump()))
    db.flush()
