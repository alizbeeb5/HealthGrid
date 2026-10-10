"""Validate source linkage and catalog applicability; evidence is not truth proof."""

import re
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.modules.intelligence.catalog import ReportCatalog
from app.modules.intelligence.schemas import Evidence


class InvalidProposal(ValueError):
    """Provider output is not suitable for showing as a validated proposal."""


def _leaves(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            # report_text is preserved verbatim by the caller, not an extracted fact.
            if key != "report_text":
                yield from _leaves(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaves(child, f"{path}.{index}")
    elif value is not None:
        yield path, value


def _mentions(excerpts: list[str], tokens: list[str]) -> bool:
    return any(
        re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", excerpt, re.I)
        for excerpt in excerpts
        for token in tokens
    )


def validate_proposal(
    candidate: BaseModel,
    evidence: list[Evidence],
    report_text: str,
    catalog: ReportCatalog,
) -> list[str]:
    """Reject unsupported fields; return questions for incomplete legitimate drafts.

    The backend's IncidentDraftInput validates shape and cross-field constraints.
    This validator separately verifies every non-null/nonempty scalar's exact
    source excerpt and checks IDs, applicability, units and absolute counts.
    """
    data = candidate.model_dump(mode="json")
    if data.get("report_text") != report_text:
        raise InvalidProposal("Candidate must preserve the original report text.")
    leaves = dict(_leaves(data))
    linked: dict[str, list[str]] = {}
    for entry in evidence:
        if not entry.source_excerpt.strip() or entry.source_excerpt not in report_text:
            raise InvalidProposal("Evidence excerpts must be exact nonblank report substrings.")
        if entry.field_path not in leaves:
            raise InvalidProposal(f"Evidence points to an absent field: {entry.field_path}.")
        linked.setdefault(entry.field_path, []).append(entry.source_excerpt)
    for path in leaves:
        if path not in linked:
            raise InvalidProposal(f"Missing evidence for extracted field {path}.")

    for field in ("starts_at", "expected_ends_at"):
        if data.get(field) is not None:
            actual = datetime.fromisoformat(data[field]).astimezone(UTC)
            matches = [
                datetime.fromisoformat(token).astimezone(UTC)
                for excerpt in linked[field]
                for token in re.findall(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})",
                    excerpt,
                )
            ]
            if actual not in matches:
                raise InvalidProposal(
                    "Date/time requires explicit matching ISO timestamp evidence."
                )

    if data.get("starts_at") and data.get("expected_ends_at"):
        if datetime.fromisoformat(data["expected_ends_at"]) <= datetime.fromisoformat(
            data["starts_at"]
        ):
            raise InvalidProposal("Expected end must be later than the incident start.")

    snapshots = {s.facility.facility_id: s for s in catalog.snapshots}
    definitions = {r.resource_id: r for r in catalog.resources}
    affected = data.get("affected_facility_ids", [])
    if len(affected) != len(set(affected)) or affected != sorted(affected):
        raise InvalidProposal("Affected facilities must be sorted and unique.")
    for index, facility_id in enumerate(affected):
        snapshot = snapshots.get(facility_id)
        if snapshot is None:
            raise InvalidProposal("Unknown affected facility.")
        tokens = [facility_id]
        # An ambiguous duplicate display name does not resolve an ID.
        if (
            sum(
                s.facility.name.casefold() == snapshot.facility.name.casefold()
                for s in snapshots.values()
            )
            == 1
        ):
            tokens.append(snapshot.facility.name)
        if not _mentions(linked[f"affected_facility_ids.{index}"], tokens):
            raise InvalidProposal("Facility ID lacks unambiguous catalog name/ID evidence.")
    service_id = data.get("service_id")
    all_services = [s for snapshot in snapshots.values() for s in snapshot.services]
    known_services = {s.service_id: s.name for s in all_services}
    if service_id is not None:
        if service_id not in known_services or not _mentions(
            linked["service_id"], [service_id, known_services[service_id]]
        ):
            raise InvalidProposal("Selected service is unknown or lacks source linkage.")
        for facility_id in affected:
            if not any(s.service_id == service_id for s in snapshots[facility_id].services):
                raise InvalidProposal("Affected facility does not offer the selected service.")

    seen = set()
    for kind in ("service_overrides", "resource_overrides"):
        id_key = "service_id" if kind == "service_overrides" else "resource_id"
        for index, override in enumerate(data.get(kind, [])):
            prefix = f"{kind}.{index}"
            facility_id, identifier = override["facility_id"], override[id_key]
            if facility_id not in affected:
                raise InvalidProposal("Override facility must be in affected_facility_ids.")
            key = kind, facility_id, identifier
            if key in seen:
                raise InvalidProposal("Duplicate override.")
            seen.add(key)
            if not _mentions(
                linked[f"{prefix}.facility_id"], [facility_id, snapshots[facility_id].facility.name]
            ):
                raise InvalidProposal("Override facility lacks source linkage.")
            if kind == "service_overrides":
                if identifier != service_id:
                    raise InvalidProposal("Override service must equal the selected service.")
                if not _mentions(
                    linked[f"{prefix}.service_id"], [identifier, known_services[identifier]]
                ):
                    raise InvalidProposal("Override service lacks source linkage.")
                if not _mentions(linked[f"{prefix}.status"], [override["status"]]):
                    raise InvalidProposal("Service status requires an explicit source statement.")
                if override["status"] == "limited" and not override.get("restriction_note", ""):
                    raise InvalidProposal("A limited service requires a restriction note.")
            else:
                resource = definitions.get(identifier)
                if resource is None or not any(
                    r.resource_id == identifier for r in snapshots[facility_id].resources
                ):
                    raise InvalidProposal("Resource is unknown or inapplicable to facility.")
                if not _mentions(linked[f"{prefix}.resource_id"], [identifier, resource.name]):
                    raise InvalidProposal("Resource ID lacks catalog name/ID source evidence.")
                if not _mentions(linked[f"{prefix}.unit"], [resource.unit.value]):
                    raise InvalidProposal("Resource unit lacks explicit source evidence.")
                if override["unit"] != resource.unit.value:
                    raise InvalidProposal("Resource unit does not match the catalog.")
                quantity = Decimal(str(override["available_quantity"]))
                if not quantity.is_finite() or quantity < 0:
                    raise InvalidProposal("Quantity must be nonnegative and finite.")
                if not resource.allows_fractional and quantity != quantity.to_integral_value():
                    raise InvalidProposal("This resource requires a whole quantity.")
                excerpts = linked[f"{prefix}.available_quantity"]
                tokens = [str(quantity)]
                if quantity == quantity.to_integral_value():
                    tokens.append(str(int(quantity)))
                if not _mentions(excerpts, tokens):
                    raise InvalidProposal(
                        "Absolute resource quantity lacks numeric source evidence."
                    )
                if any(
                    re.search(r"\b(lost|loss|destroyed|damaged|subtract)\b", e, re.I)
                    for e in excerpts
                ):
                    raise InvalidProposal("A resource loss is not an absolute available quantity.")

    questions = []
    if not affected:
        questions.append("Which hospital IDs are affected?")
    if service_id is None:
        questions.append("Which service is affected?")
    if data.get("starts_at") is None:
        questions.append("What is the incident start date, time and timezone?")
    if not data.get("service_overrides") and not data.get("resource_overrides"):
        questions.append("What service status or absolute resource availability should be assumed?")
    return questions
