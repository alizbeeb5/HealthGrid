"""Provider tests use synthetic reports and stubs; never execute paid model calls."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as Object
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.modules.facilities.schemas import FacilitySnapshotResponse
from app.modules.facilities.schemas import ResourceDefinition as CatalogResource
from app.modules.intelligence.adapter import QUESTIONS, OpenAIReportProvider
from app.modules.intelligence.catalog import ReportCatalog
from app.modules.intelligence.config import IntelligenceSettings
from app.modules.intelligence.schemas import ExtractionProposal, ReportRequest
from app.modules.intelligence.service import assess_report, extract_report
from app.modules.scenarios.schemas import IncidentDraftInput

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads((ROOT / "data/synthetic/feature-5/report-cases.json").read_text())


@pytest.fixture
def catalog():
    examples = ROOT / "contracts/examples/feature-1"
    return ReportCatalog(
        tuple(
            FacilitySnapshotResponse.model_validate(
                json.loads((examples / f"DEMO-{letter}.snapshot.response.json").read_text())
            )
            for letter in "ABC"
        ),
        tuple(
            CatalogResource.model_validate(row)
            for row in json.loads((examples / "resource-definitions.json").read_text())
        ),
    )


@pytest.fixture
def settings():
    return IntelligenceSettings(
        _env_file=None, openai_api_key="test-key-not-real", openai_extraction_model="gpt-6-luna"
    )


def run(coroutine):
    return asyncio.run(coroutine)


def extraction_result(proposal, status="completed", refusal=False):
    return Object(
        status=status,
        model="gpt-6-luna",
        output=[Object(content=[Object(type="refusal")])] if refusal else [],
        output_parsed=proposal,
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case"])
def test_six_reports_return_supported_proposals_and_questions(catalog, settings, case):
    provider = Object(extract=AsyncMock(return_value=extraction_result(case["proposal"])))
    before = deepcopy(case)
    result = run(
        extract_report(case["report_text"], catalog, IncidentDraftInput, settings, provider)
    )
    assert result.extraction_status == "completed"
    assert result.candidate.report_text == case["report_text"]
    assert result.candidate.resource_overrides == []  # lost count is never absolute availability
    for term in case["expected_question_terms"]:
        assert any(term in question for question in result.questions)
    assert result.elapsed_ms >= 0 and result.model == "gpt-6-luna"
    assert case == before
    assert not hasattr(result, "confirmed")


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case"])
def test_four_fixed_assessment_answers_and_metadata(catalog, settings, case):
    answers = [
        Object(type="choice", name=name, choice=value)
        for name, value in reversed(list(case["expected_answers"].items()))
    ]
    provider = Object(assess=AsyncMock(return_value=Object(answers=answers, model="gpt-6-luna")))
    result = run(assess_report(case["report_text"], catalog, settings, provider))
    assert result.assessment_status == "completed"
    assert [answer.name for answer in result.answers] == list(QUESTIONS)
    assert {a.name: a.value for a in result.answers} == case["expected_answers"]
    assert result.rubric_version == "emergency-review-v1" and result.elapsed_ms >= 0


def test_missing_key_does_not_call_provider_or_require_catalog(settings):
    settings.openai_api_key = ""
    provider = Object(assess=AsyncMock(), extract=AsyncMock())
    assess = run(assess_report(CASES[0]["report_text"], ReportCatalog((), ()), settings, provider))
    extract = run(
        extract_report(
            CASES[0]["report_text"], ReportCatalog((), ()), IncidentDraftInput, settings, provider
        )
    )
    assert assess.assessment_status == extract.extraction_status == "unavailable"
    assert extract.candidate is None and not assess.answers
    provider.assess.assert_not_called()
    provider.extract.assert_not_called()


def test_assessment_partial_and_full_refusals(catalog, settings):
    for refusal_count in (1, 4):
        answers = [
            Object(type="refusal", name=name)
            if index < refusal_count
            else Object(type="choice", name=name, choice="no")
            for index, name in enumerate(QUESTIONS)
        ]
        provider = Object(
            assess=AsyncMock(return_value=Object(answers=answers, model="gpt-6-luna"))
        )
        result = run(assess_report(CASES[0]["report_text"], catalog, settings, provider))
        assert result.assessment_status == ("refused" if refusal_count == 4 else "completed")
        assert (
            sum(a.value is None and a.answer_status == "refused" for a in result.answers)
            == refusal_count
        )


@pytest.mark.parametrize(
    "answers",
    [
        [],
        [Object(type="choice", name="other", choice="yes")],
        [Object(type="choice", name=name, choice="invented") for name in QUESTIONS],
    ],
)
def test_malformed_assessments_fail(catalog, settings, answers):
    provider = Object(assess=AsyncMock(return_value=Object(answers=answers, model="gpt-6-luna")))
    result = run(assess_report(CASES[0]["report_text"], catalog, settings, provider))
    assert result.assessment_status == "failed" and result.answers == []


@pytest.mark.parametrize(
    "status,refusal,expected",
    [
        ("completed", True, "refused"),
        ("incomplete", False, "failed"),
        ("completed", False, "failed"),
    ],
)
def test_extraction_refusal_and_incomplete_states(catalog, settings, status, refusal, expected):
    provider = Object(extract=AsyncMock(return_value=extraction_result(None, status, refusal)))
    result = run(
        extract_report(CASES[0]["report_text"], catalog, IncidentDraftInput, settings, provider)
    )
    assert result.extraction_status == expected
    assert result.candidate is None and result.evidence == []


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-evidence",
        "nonliteral-excerpt",
        "bad-path",
        "unknown-id",
        "report-rewritten",
        "wrong-unit",
        "fractional-count",
        "loss-is-not-availability",
    ],
)
def test_invalid_proposals_never_reach_review_as_success(catalog, settings, mutation):
    case = deepcopy(CASES[0])
    proposal = case["proposal"]
    if mutation == "missing-evidence":
        proposal["evidence"] = []
    elif mutation == "nonliteral-excerpt":
        proposal["evidence"][0]["source_excerpt"] = "Not in this report"
    elif mutation == "bad-path":
        proposal["evidence"][0]["field_path"] = "title.does.not.exist"
    elif mutation == "unknown-id":
        proposal["candidate"]["affected_facility_ids"] = ["DEMO-X"]
    elif mutation == "report-rewritten":
        proposal["candidate"]["report_text"] = "Different report"
    else:
        case = deepcopy(CASES[4])
        proposal = case["proposal"]
        proposal["candidate"]["resource_overrides"] = [
            {
                "facility_id": "DEMO-B",
                "resource_id": "working-monitors",
                "available_quantity": 2,
                "unit": "item",
            }
        ]
        if mutation == "wrong-unit":
            proposal["candidate"]["resource_overrides"][0]["unit"] = "liter"
        if mutation == "fractional-count":
            proposal["candidate"]["resource_overrides"][0]["available_quantity"] = 1.5
        proposal["evidence"].extend(
            {"field_path": f"resource_overrides.0.{field}", "source_excerpt": case["report_text"]}
            for field in proposal["candidate"]["resource_overrides"][0]
        )
    provider = Object(extract=AsyncMock(return_value=extraction_result(proposal)))
    result = run(
        extract_report(case["report_text"], catalog, IncidentDraftInput, settings, provider)
    )
    assert result.extraction_status == "failed" and result.candidate is None
    assert not result.evidence


def test_provider_failure_and_timeout_preserve_manual_inputs(catalog, settings):
    report = CASES[0]["report_text"]
    manual = deepcopy(CASES[0]["proposal"]["candidate"])
    before = deepcopy(manual)
    provider = Object(
        assess=AsyncMock(side_effect=RuntimeError("secret provider details")),
        extract=AsyncMock(side_effect=RuntimeError("secret provider details")),
    )
    assert run(assess_report(report, catalog, settings, provider)).assessment_status == "failed"
    result = run(extract_report(report, catalog, IncidentDraftInput, settings, provider))
    assert result.extraction_status == "failed"
    assert "secret" not in result.model_dump_json()
    assert manual == before

    async def slow(*args):
        await asyncio.sleep(1)

    settings.openai_intelligence_timeout_seconds = 0.005
    provider = Object(assess=slow, extract=slow)
    assert run(assess_report(report, catalog, settings, provider)).assessment_status == "failed"
    assert (
        run(
            extract_report(report, catalog, IncidentDraftInput, settings, provider)
        ).extraction_status
        == "failed"
    )


def test_sdk_requests_use_actual_api_shapes_without_tools(catalog):
    client = Object(decisions=Object(create=AsyncMock()), responses=Object(parse=AsyncMock()))
    provider = OpenAIReportProvider(client)
    run(provider.assess(CASES[5]["report_text"], catalog, "gpt-6-luna"))
    kwargs = client.decisions.create.call_args.kwargs
    assert len(kwargs["questions"]) == 4
    assert all(question["type"] == "choice" for question in kwargs["questions"])
    assert all(
        [choice["value"] for choice in question["choices"]] == ["yes", "no", "unclear"]
        for question in kwargs["questions"]
    )
    assert json.loads(kwargs["input"])["report_text"] == CASES[5]["report_text"]
    run(
        provider.extract(
            CASES[5]["report_text"], catalog, "gpt-6-luna", ExtractionProposal[IncidentDraftInput]
        )
    )
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs["tools"] == [] and kwargs["store"] is False
    output_model = kwargs["text_format"]
    assert issubclass(output_model, ExtractionProposal[IncidentDraftInput])
    # Exercise the actual SDK serialization: this formerly emitted an invalid
    # generic class name and OpenAI rejected the request before generation.
    import re

    from openai.lib._parsing._responses import type_to_text_format_param

    provider_format = type_to_text_format_param(output_model)
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", provider_format["name"])
    assert provider_format["strict"] is True
    assert (
        provider_format["schema"]["$defs"]["IncidentDraftInput"]
        == (
            ExtractionProposal[IncidentDraftInput].model_json_schema()["$defs"][
                "IncidentDraftInput"
            ]
        )
    )
    assert len(kwargs["input"]) == 1 and kwargs["input"][0]["role"] == "user"


@pytest.mark.parametrize("text", ["", "  ", "x" * 10_001])
def test_invalid_report_rejected_before_provider(text, catalog, settings):
    with pytest.raises(ValidationError):
        ReportRequest(report_text=text)
    provider = Object(assess=AsyncMock())
    with pytest.raises(ValidationError):
        run(assess_report(text, catalog, settings, provider))
    provider.assess.assert_not_called()


def test_valid_absolute_resource_override_and_loss_rejection(catalog, settings):
    from app.modules.intelligence.schemas import Evidence
    from app.modules.intelligence.validation import InvalidProposal, validate_proposal

    for lost in (False, True):
        report = (
            "Demo Hospital B Emergency care has 2 Working monitors item "
            + ("lost." if lost else "available.")
            + " Starts at 2026-10-10T10:00:00Z."
        )
        data = deepcopy(CASES[4]["proposal"]["candidate"])
        data["title"] = report.split(".")[0]
        data["report_text"] = report
        data["resource_overrides"] = [
            {
                "facility_id": "DEMO-B",
                "resource_id": "working-monitors",
                "available_quantity": 2,
                "unit": "item",
            }
        ]
        evidence = [
            Evidence(field_path=entry["field_path"], source_excerpt=report)
            for entry in CASES[4]["proposal"]["evidence"]
        ]
        evidence.extend(
            Evidence(field_path=f"resource_overrides.0.{field}", source_excerpt=report)
            for field in data["resource_overrides"][0]
        )
        if lost:
            with pytest.raises(InvalidProposal, match="loss"):
                validate_proposal(
                    IncidentDraftInput.model_validate(data), evidence, report, catalog
                )
        else:
            assert not validate_proposal(
                IncidentDraftInput.model_validate(data), evidence, report, catalog
            )


def test_invented_dates_and_status_rejected(catalog, settings):
    for field, value in (
        ("starts_at", "2026-10-11T10:00:00Z"),
        ("expected_ends_at", "2026-10-10T17:00:00Z"),
    ):
        proposal = deepcopy(CASES[0]["proposal"])
        proposal["candidate"][field] = value
        provider = Object(extract=AsyncMock(return_value=extraction_result(proposal)))
        result = run(
            extract_report(CASES[0]["report_text"], catalog, IncidentDraftInput, settings, provider)
        )
        assert result.extraction_status == "failed" and result.candidate is None
    proposal = deepcopy(CASES[0]["proposal"])
    proposal["candidate"]["service_overrides"][0]["status"] = "operating"
    provider = Object(extract=AsyncMock(return_value=extraction_result(proposal)))
    assert (
        run(
            extract_report(CASES[0]["report_text"], catalog, IncidentDraftInput, settings, provider)
        ).extraction_status
        == "failed"
    )


def test_missing_extraction_model_keeps_assessment_independent(catalog, settings):
    settings.openai_extraction_model = None
    provider = Object(extract=AsyncMock())
    result = run(
        extract_report(CASES[0]["report_text"], catalog, IncidentDraftInput, settings, provider)
    )
    assert result.extraction_status == "unavailable"
    provider.extract.assert_not_called()


def test_sdk_client_disables_retries_and_has_timeout(settings, monkeypatch):
    from contextlib import asynccontextmanager

    from app.modules.intelligence import adapter

    calls = []

    @asynccontextmanager
    async def fake_client(**kwargs):
        calls.append(kwargs)
        yield Object()

    monkeypatch.setattr(adapter, "AsyncOpenAI", fake_client)

    async def inspect_client():
        async with adapter.openai_provider(settings):
            pass

    run(inspect_client())
    assert calls[0]["max_retries"] == 0
    assert calls[0]["timeout"] == 15


def test_api_routes_without_key_and_invalid_inputs():
    from datetime import UTC, datetime

    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    from app.core.database import get_session
    from app.modules.facilities.router import server_now
    from app.modules.intelligence.router import (
        IntelligenceRoute,
        bind_extraction_route,
        intelligence_settings,
        router,
    )

    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    extraction = APIRouter(prefix="/intelligence", route_class=IntelligenceRoute)
    bind_extraction_route(IncidentDraftInput, extraction)
    application.dependency_overrides[intelligence_settings] = lambda: IntelligenceSettings(
        _env_file=None,
        openai_api_key="",
        openai_extraction_model=None,
    )
    # No database access should be needed to produce missing-key component states.
    application.dependency_overrides[get_session] = lambda: None
    application.dependency_overrides[server_now] = lambda: datetime(2026, 10, 10, tzinfo=UTC)
    with TestClient(application) as client:
        for path, status_field in (
            ("assess", "assessment_status"),
            ("extract", "extraction_status"),
        ):
            response = client.post(
                f"/api/v1/intelligence/incidents/{path}",
                json={"report_text": CASES[0]["report_text"]},
            )
            assert response.status_code == 200
            assert response.json()[status_field] == "unavailable"
            for body in (
                {},
                {"report_text": ""},
                {"report_text": "   "},
                {"report_text": "x" * 10_001},
                {"report_text": "ok", "extra": 1},
            ):
                response = client.post(f"/api/v1/intelligence/incidents/{path}", json=body)
                assert response.status_code == 422
                assert response.json()["error"]["code"] == "invalid_request"
    with pytest.raises(ValueError, match="already bound"):
        bind_extraction_route(IncidentDraftInput, extraction)


def test_provider_initialization_failure_is_component_failure(catalog, settings, monkeypatch):
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime

    from fastapi import APIRouter

    from app.modules.intelligence import router as routes

    @asynccontextmanager
    async def broken_provider(settings):
        raise RuntimeError("private initialization details")
        yield  # pragma: no cover

    monkeypatch.setattr(routes, "load_report_catalog", lambda db, now: catalog)
    monkeypatch.setattr(routes, "openai_provider", broken_provider)
    request = ReportRequest(report_text=CASES[0]["report_text"])
    now = datetime(2026, 10, 10, tzinfo=UTC)
    result = run(routes.assess_incident(request, settings, None, now))
    assert result.assessment_status == "failed"
    extraction = APIRouter(prefix="/intelligence")
    routes.bind_extraction_route(IncidentDraftInput, extraction)
    result = run(extraction.routes[0].endpoint(request, settings, None, now))
    assert result.extraction_status == "failed" and result.candidate is None
    assert "private" not in result.model_dump_json()


def test_extracted_proposal_can_be_reviewed_saved_and_simulated(
    client, catalog, settings, monkeypatch
):
    from contextlib import asynccontextmanager

    from app.modules.intelligence import router as routes

    provider = Object(extract=AsyncMock(return_value=extraction_result(CASES[0]["proposal"])))

    @asynccontextmanager
    async def stub_provider(configuration):
        yield provider

    monkeypatch.setattr(routes, "openai_provider", stub_provider)
    # The real route loads its catalog from the disposable database. Only the
    # provider is stubbed; the incident/capacity/simulation services are real.
    from app.main import app

    app.dependency_overrides[routes.intelligence_settings] = lambda: settings
    extracted = client.post(
        "/api/v1/intelligence/incidents/extract", json={"report_text": CASES[0]["report_text"]}
    )
    assert extracted.status_code == 200, extracted.text
    result = extracted.json()
    assert result["extraction_status"] == "completed"
    candidate = result["candidate"]
    IncidentDraftInput.model_validate(candidate)
    draft = client.post("/api/v1/scenarios/incidents", json=candidate)
    assert draft.status_code == 201, draft.text
    saved = draft.json()
    assert saved["status"] == "draft" and saved["baseline_id"] is None
    confirmed = client.post(
        f"/api/v1/scenarios/incidents/{saved['incident_id']}/confirm",
        json={
            "draft_revision_id": saved["revision_id"],
            "input": candidate,
            "confirmed_by": "Demo planner",
        },
    )
    assert confirmed.status_code == 201, confirmed.text
    revision = confirmed.json()
    simulation = client.post(
        f"/api/v1/scenarios/incidents/{revision['incident_id']}/revisions/"
        f"{revision['revision_id']}/simulate"
    )
    assert simulation.status_code == 201, simulation.text
    run_result = simulation.json()
    hospital_b = next(
        row for row in run_result["impact"]["rows"] if row["facility"]["facility_id"] == "DEMO-B"
    )
    assert hospital_b["baseline_capacity"]["estimated_capacity"] == 5
    assert hospital_b["scenario_capacity"]["estimated_capacity"] == 0
    assert hospital_b["capacity_change"] == -5
    snapshot = client.get("/api/v1/facilities/DEMO-B/snapshot").json()
    assert snapshot["services"][0]["status"] == "operating"
    reopened = client.get(f"/api/v1/scenarios/runs/{run_result['run_id']}")
    assert reopened.status_code == 200 and reopened.json() == run_result


def test_canonical_draft_is_exposed_in_openapi():
    from app.main import app

    document = app.openapi()
    response = document["paths"]["/api/v1/intelligence/incidents/extract"]["post"]["responses"][
        "200"
    ]
    name = response["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
    candidate = document["components"]["schemas"][name]["properties"]["candidate"]
    assert {"$ref": "#/components/schemas/IncidentDraftInput"} in candidate["anyOf"]
