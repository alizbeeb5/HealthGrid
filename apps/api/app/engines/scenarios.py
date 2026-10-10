"""Pure incident overlay: baseline vs scenario capacity through the capacity engine.

No database, HTTP, clock or AI calls. Inputs are never mutated. Scenario resource
quantities are planner assumptions: they carry no observation ID or timestamp, so
the old report is never presented as evidence for the new value.
"""

from app.engines.capacity import calculate_service_capacity
from app.modules.facilities.schemas import DataStatus, FacilitySnapshotResponse
from app.modules.scenarios.schemas import (
    AppliedResourceOverride,
    AppliedServiceOverride,
    ImpactRow,
    IncidentBaseline,
    IncidentImpact,
    IncidentRevision,
    RevisionStatus,
)

ENGINE_VERSION = "incident-overlay-v1"


def simulate_incident(baseline: IncidentBaseline, incident: IncidentRevision) -> IncidentImpact:
    if incident.status != RevisionStatus.CONFIRMED or incident.baseline_id != baseline.baseline_id:
        raise ValueError("Simulate a confirmed revision against its own baseline.")
    selected = incident.input.service_id
    if selected != baseline.service_id:
        raise ValueError("The incident and baseline must use the same service.")
    profiles = {profile.service_id: profile for profile in baseline.requirement_profiles}
    profile = profiles.get(selected)
    required = {r.resource_id for r in profile.requirements} if profile else set()
    affected = set(incident.input.affected_facility_ids)
    snapshot_ids = {s.facility.facility_id for s in baseline.facility_snapshots}
    if not affected <= snapshot_ids:
        raise ValueError("Affected facilities must be in the baseline.")

    rows = []
    for snapshot in baseline.facility_snapshots:
        facility_id = snapshot.facility.facility_id
        service = next((s for s in snapshot.services if s.service_id == selected), None)
        if service is None:
            raise ValueError(f"Baseline facility {facility_id} does not offer {selected}.")
        before = calculate_service_capacity(snapshot, service, profile)
        if facility_id not in affected:
            rows.append(ImpactRow(facility=snapshot.facility, baseline_capacity=before,
                                  scenario_capacity=before, capacity_change=None
                                  if before.estimated_capacity is None else 0,
                                  affected=False, applied_overrides=[]))
            continue

        scenario, applied = apply_incident_overrides(snapshot, incident, selected, required)
        scenario_service = next(s for s in scenario.services if s.service_id == selected)
        after = calculate_service_capacity(scenario, scenario_service, profile)
        change = (
            after.estimated_capacity - before.estimated_capacity
            if before.estimated_capacity is not None and after.estimated_capacity is not None
            else None
        )
        rows.append(ImpactRow(facility=snapshot.facility, baseline_capacity=before,
                              scenario_capacity=after, capacity_change=change,
                              affected=True, applied_overrides=applied))

    return IncidentImpact(
        incident_id=incident.incident_id,
        revision_id=incident.revision_id,
        baseline_id=baseline.baseline_id,
        baseline_captured_at=baseline.captured_at,
        service_id=selected,
        capacity_unit="simultaneous_service_place",
        rows=rows,
    )


def apply_incident_overrides(
    snapshot: FacilitySnapshotResponse,
    incident: IncidentRevision,
    service_id: str,
    required: set[str],
) -> tuple[FacilitySnapshotResponse, list]:
    """One facility's snapshot under the incident's confirmed overrides (a copy)."""
    facility_id = snapshot.facility.facility_id
    services = list(snapshot.services)
    resources = list(snapshot.resources)
    applied: list = []

    for override in incident.input.service_overrides:
        if override.facility_id != facility_id:
            continue
        if override.service_id != service_id:
            raise ValueError("Service overrides must use the incident's service.")
        index = next(i for i, s in enumerate(services) if s.service_id == service_id)
        applied.append(AppliedServiceOverride(
            override_type="service_status",
            service_id=service_id,
            baseline_status=services[index].status,
            scenario_status=override.status,
            restriction_note=override.restriction_note,
        ))
        services[index] = services[index].model_copy(update={"status": override.status})

    for override in sorted(incident.input.resource_overrides, key=lambda o: o.resource_id):
        if override.facility_id != facility_id:
            continue
        index = next(
            (i for i, r in enumerate(resources) if r.resource_id == override.resource_id), None
        )
        if index is None:
            raise ValueError(f"{override.resource_id} is not tracked for {facility_id}.")
        reported = resources[index]
        if override.unit != reported.unit:
            raise ValueError(f"Unit mismatch for {override.resource_id}.")
        applied.append(AppliedResourceOverride(
            override_type="resource_quantity",
            resource_id=override.resource_id,
            unit=override.unit,
            baseline_quantity=reported.available_quantity,
            baseline_data_status=reported.data_status,
            scenario_quantity=override.available_quantity,
            affects_modeled_estimate=override.resource_id in required,
        ))
        # An explicit assumption: usable as current, with no observation provenance.
        resources[index] = reported.model_copy(update={
            "available_quantity": override.available_quantity,
            "observation_id": None,
            "observed_at": None,
            "recorded_at": None,
            "data_status": DataStatus.CURRENT,
        })

    scenario = snapshot.model_copy(update={"services": services, "resources": resources})
    return scenario, applied
