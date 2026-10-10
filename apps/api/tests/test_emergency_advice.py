"""Emergency guidance is stateless, uses live evidence, and never allocates resources."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace as Object
from unittest.mock import AsyncMock

import pytest

from app.main import app
from app.modules.intelligence import router as routes
from app.modules.intelligence.adapter import OpenAIReportProvider
from app.modules.intelligence.advice_schemas import (
    EmergencyAdviceProposal,
    EmergencyAdviceRequest,
    EmergencyAdviceResponse,
)
from app.modules.intelligence.config import IntelligenceSettings
from app.modules.intelligence.emergency import emergency_advice

EXAMPLES = Path(__file__).resolve().parents[3] / "contracts/examples/feature-5"
NOW = datetime(2026, 10, 10, 9, tzinfo=UTC)


def example(name):
    return json.loads((EXAMPLES / name).read_text())


def settings(key="fictional-test-key"):
    return IntelligenceSettings(_env_file=None, openai_api_key=key)


def result(proposal):
    return Object(status="completed", model="gpt-6-luna", output=[], output_parsed=proposal)


def stub(monkeypatch, provider):
    @asynccontextmanager
    async def context(configuration):
        yield provider

    monkeypatch.setattr(routes, "openai_provider", context)
    app.dependency_overrides[routes.intelligence_settings] = settings


def test_advice_route_uses_real_snapshot_and_engine_without_writes(client, monkeypatch):
    proposal = example("emergency-advice.response.json")["proposal"]
    provider = Object(advise=AsyncMock(return_value=result(proposal)))
    stub(monkeypatch, provider)
    before = client.get("/api/v1/facilities/DEMO-B/snapshot").json()
    response = client.post(
        "/api/v1/intelligence/incidents/advice", json=example("emergency-advice.request.json")
    )
    assert response.status_code == 200, response.text
    body = EmergencyAdviceResponse.model_validate(response.json())
    assert body.advice_status == "completed"
    context, model = provider.advise.call_args.args
    assert model == "gpt-6-luna"
    assert context["incident_status"] == "unconfirmed_draft"
    hospitals = context["hospitals"]
    assert hospitals["DEMO-B"]["reported_capacities"][0]["estimated_capacity"] == 5
    assert hospitals["DEMO-A"]["reported_capacities"][0]["estimated_capacity"] is None
    assert hospitals["DEMO-C"]["reported_capacities"][0]["estimated_capacity"] == 0
    assert hospitals["DEMO-B"]["snapshot"] == before
    assert all(row["snapshot"]["as_of"] == before["as_of"] for row in hospitals.values())
    assert client.get("/api/v1/facilities/DEMO-B/snapshot").json() == before
    assert client.get("/api/v1/scenarios/incidents").json()["items"] == []


@pytest.mark.parametrize("fault", ["unknown_hospital", "invented_evidence", "container_evidence"])
def test_unverifiable_guidance_fails_without_exposing_proposal(client, monkeypatch, fault):
    proposal = example("emergency-advice.response.json")["proposal"]
    if fault == "unknown_hospital":
        proposal["actions"][0]["facility_ids"] = ["INVENTED"]
    else:
        path = (
            "hospitals.DEMO-A.reported_capacities"
            if (fault == "container_evidence")
            else "hospitals.DEMO-B.invented_inventory"
        )
        proposal["actions"][0]["evidence_paths"] = [path]
    stub(monkeypatch, Object(advise=AsyncMock(return_value=result(proposal))))
    response = client.post(
        "/api/v1/intelligence/incidents/advice", json=example("emergency-advice.request.json")
    )
    assert response.json()["advice_status"] == "failed"
    assert response.json()["proposal"] is None and response.json()["evidence"] == []


def test_invalid_incident_has_field_errors_before_provider_call(client, monkeypatch):
    provider = Object(advise=AsyncMock())
    stub(monkeypatch, provider)
    request = example("emergency-advice.request.json")
    request["incident"]["affected_facility_ids"] = ["INVENTED"]
    response = client.post("/api/v1/intelligence/incidents/advice", json=request)
    assert response.status_code == 422
    assert any(row["field"].startswith("incident.") for row in response.json()["error"]["fields"])
    provider.advise.assert_not_called()


def test_supplied_missing_data_and_unknown_values_are_valid_evidence(client, monkeypatch):
    proposal = example("emergency-advice.response.json")["proposal"]
    paths = [
        "incident_status",
        "missing_operational_data.0",
        "hospitals.DEMO-A.reported_capacities.0.estimated_capacity",
    ]
    proposal["actions"][0]["evidence_paths"] = paths
    stub(monkeypatch, Object(advise=AsyncMock(return_value=result(proposal))))
    response = client.post(
        "/api/v1/intelligence/incidents/advice", json=example("emergency-advice.request.json")
    )
    assert response.json()["advice_status"] == "completed"
    evidence = {item["path"]: item["value"] for item in response.json()["evidence"]}
    assert evidence[paths[0]] == "unconfirmed_draft"
    assert evidence[paths[1]] == "occupancy"
    assert evidence[paths[2]] is None


@pytest.mark.parametrize("state", ["missing_key", "refused", "incomplete", "transport"])
def test_independent_failure_states(state):
    request = EmergencyAdviceRequest.model_validate(example("emergency-advice.request.json"))
    returned = result(None)
    returned.status = "incomplete"
    if state == "refused":
        returned.output = [Object(content=[Object(type="refusal")])]
    provider = Object(advise=AsyncMock(return_value=returned))
    if state == "transport":
        provider.advise.side_effect = RuntimeError("private-provider-detail")
    response = asyncio.run(
        emergency_advice(
            request, {}, settings("" if state == "missing_key" else "fictional-key"), NOW, provider
        )
    )
    expected = {"missing_key": "unavailable", "refused": "refused"}.get(state, "failed")
    assert response.advice_status == expected
    assert response.proposal is None
    assert "private-provider-detail" not in response.model_dump_json()
    if state == "missing_key":
        provider.advise.assert_not_called()


def test_adapter_uses_same_responses_client_and_bounded_structured_output():
    parse = AsyncMock(return_value=result(None))
    provider = OpenAIReportProvider(Object(responses=Object(parse=parse)))
    asyncio.run(provider.advise({"incident": {"report_text": "fictional outage"}}, "gpt-6-luna"))
    kwargs = parse.call_args.kwargs
    assert kwargs["text_format"] is EmergencyAdviceProposal
    assert kwargs["store"] is False and kwargs["tools"] == []
    assert kwargs["reasoning"] == {"effort": "none"}
    assert kwargs["max_output_tokens"] == 1800
