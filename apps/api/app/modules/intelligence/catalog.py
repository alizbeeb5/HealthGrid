"""Request-local allowed catalog context, supplied through public facility services."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.facilities import service as facilities
from app.modules.facilities.schemas import FacilitySnapshotResponse, ResourceDefinition


@dataclass(frozen=True)
class ReportCatalog:
    snapshots: tuple[FacilitySnapshotResponse, ...]
    resources: tuple[ResourceDefinition, ...]

    def provider_context(self) -> dict:
        return {
            "facilities": [
                {
                    "facility_id": snapshot.facility.facility_id,
                    "name": snapshot.facility.name,
                    "services": [
                        {"service_id": s.service_id, "name": s.name} for s in snapshot.services
                    ],
                    "applicable_resource_ids": [r.resource_id for r in snapshot.resources],
                }
                for snapshot in self.snapshots
            ],
            "resources": [resource.model_dump(mode="json") for resource in self.resources],
        }


def load_report_catalog(db: Session, now: datetime) -> ReportCatalog:
    return ReportCatalog(
        snapshots=tuple(
            facilities.get_snapshot(db, row.facility_id, now)
            for row in facilities.list_facilities(db).items
        ),
        resources=tuple(facilities.list_resource_definitions(db)),
    )
