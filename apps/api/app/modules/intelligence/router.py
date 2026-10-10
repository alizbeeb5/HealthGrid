"""AI routes with an explicit backend draft-schema integration boundary.

Both endpoints reuse the backend-owned IncidentDraftInput. Binding occurs
before application inclusion so extraction publishes the exact shared schema.
"""

from datetime import datetime
from time import monotonic

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.modules.capacity import service as capacity
from app.modules.facilities.errors import error_response
from app.modules.facilities.router import server_now
from app.modules.facilities.schemas import FieldError
from app.modules.intelligence.adapter import openai_provider
from app.modules.intelligence.advice_schemas import (
    EmergencyAdviceRequest,
    EmergencyAdviceResponse,
)
from app.modules.intelligence.catalog import ReportCatalog, load_report_catalog
from app.modules.intelligence.config import IntelligenceSettings
from app.modules.intelligence.emergency import WARNINGS, emergency_advice
from app.modules.intelligence.failures import failure_warning
from app.modules.intelligence.schemas import (
    AssessmentResponse,
    ExtractionResponse,
    ReportRequest,
)
from app.modules.intelligence.service import assess_report, extract_report
from app.modules.scenarios.schemas import IncidentDraftInput
from app.modules.scenarios.service import validate_incident


class IntelligenceRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def contract_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                fields = []
                for issue in error.errors():
                    path = issue["loc"][1:]
                    if path and not isinstance(path[0], int):
                        field = ".".join(map(str, path))
                    else:
                        field = "report_text" if issue["type"] == "value_error" else ""
                    if field:
                        fields.append(FieldError(field=field, message=issue["msg"]))
                return error_response(422, "invalid_request", "The request is invalid.", fields)

        return contract_handler


router = APIRouter(prefix="/intelligence", tags=["intelligence"], route_class=IntelligenceRoute)


def intelligence_settings() -> IntelligenceSettings:
    return IntelligenceSettings()


@router.post("/incidents/advice", response_model=EmergencyAdviceResponse)
async def advise_incident(
    request: EmergencyAdviceRequest,
    settings: IntelligenceSettings = Depends(intelligence_settings),
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
):
    if not settings.openai_api_key.get_secret_value():
        return await emergency_advice(request, {}, settings, now)
    errors = validate_incident(db, request.incident, now, confirm=False, prefix="incident.")
    if errors:
        return error_response(422, "invalid_request", "The incident details are invalid.", errors)
    catalog = load_report_catalog(db, now)
    profiles = capacity.get_profiles(db)
    context = {
        "as_of": now.isoformat(),
        "incident": request.incident.model_dump(mode="json"),
        "incident_status": "unconfirmed_draft",
        "hospitals": {
            snapshot.facility.facility_id: {
                "snapshot": snapshot.model_dump(mode="json"),
                "reported_capacities": [
                    capacity.calculate_service(snapshot, service, profiles).model_dump(mode="json")
                    for service in snapshot.services
                    if request.incident.service_id is None
                    or service.service_id == request.incident.service_id
                ],
            }
            for snapshot in catalog.snapshots
        },
        "missing_operational_data": [
            "occupancy",
            "transfer_eligibility",
            "minimum_retained_resources",
            "transport_availability",
            "travel_times",
            "backup_power_runtime_and_consumption",
        ],
    }
    try:
        async with openai_provider(settings) as provider:
            return await emergency_advice(request, context, settings, now, provider)
    except Exception as error:
        return EmergencyAdviceResponse(
            advice_status="failed",
            proposal=None,
            evidence=[],
            warnings=[*WARNINGS, failure_warning(error, "provider")],
            model=settings.openai_emergency_model,
            elapsed_ms=0,
            as_of=now,
        )


@router.post("/incidents/assess", response_model=AssessmentResponse)
async def assess_incident(
    request: ReportRequest,
    settings: IntelligenceSettings = Depends(intelligence_settings),
    db: Session = Depends(get_session),
    now: datetime = Depends(server_now),
):
    if not settings.openai_api_key.get_secret_value():
        return await assess_report(request.report_text, ReportCatalog((), ()), settings)
    catalog = load_report_catalog(db, now)
    started = monotonic()
    try:
        async with openai_provider(settings) as provider:
            return await assess_report(request.report_text, catalog, settings, provider)
    except Exception:
        return AssessmentResponse(
            assessment_status="failed",
            answers=[],
            model=settings.openai_assessment_model,
            rubric_version="emergency-review-v1",
            elapsed_ms=max(0, round((monotonic() - started) * 1000)),
        )


def bind_extraction_route(candidate_model: type[BaseModel], target: APIRouter = router) -> None:
    """Register once before application inclusion and OpenAPI export, not at request time."""
    if any(route.path.endswith("/incidents/extract") for route in target.routes):
        raise ValueError("Extraction route is already bound.")

    async def extract_incident(
        request: ReportRequest,
        settings: IntelligenceSettings = Depends(intelligence_settings),
        db: Session = Depends(get_session),
        now: datetime = Depends(server_now),
    ):
        if not settings.openai_api_key.get_secret_value() or not settings.openai_extraction_model:
            return await extract_report(
                request.report_text, ReportCatalog((), ()), candidate_model, settings
            )
        catalog = load_report_catalog(db, now)
        started = monotonic()
        try:
            async with openai_provider(settings) as provider:
                return await extract_report(
                    request.report_text, catalog, candidate_model, settings, provider
                )
        except Exception as error:
            return ExtractionResponse[candidate_model](
                extraction_status="failed",
                candidate=None,
                evidence=[],
                questions=[],
                warnings=[failure_warning(error, "provider")],
                model=settings.openai_extraction_model,
                elapsed_ms=max(0, round((monotonic() - started) * 1000)),
            )

    target.add_api_route(
        "/incidents/extract",
        extract_incident,
        methods=["POST"],
        response_model=ExtractionResponse[candidate_model],
        operation_id="extract_incident_report",
    )


# Bind the published canonical draft before app.modules includes this router.
bind_extraction_route(IncidentDraftInput)
