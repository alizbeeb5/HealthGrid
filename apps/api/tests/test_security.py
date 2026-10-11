"""Local adversarial checks: isolated apps/database, no paid AI or load flood."""

import asyncio
import base64
import json
from urllib.parse import quote

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import Settings
from app.core.security import AdmissionLimits, SecurityMiddleware
from app.modules.allocation.schemas import AllocationRunRequest
from app.modules.investments.schemas import InvestmentRunRequest

PASSWORD = "test-only-strong-password-123"


def guarded(**overrides):
    settings = Settings(_env_file=None, **overrides)
    app = FastAPI()

    @app.get("/private")
    def private():
        return {"okay": True}

    @app.post("/api/v1/allocation/runs")
    @app.post("/echo")
    async def echo(request: Request):
        return await request.json()

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.security_allowed_hosts)
    app.add_middleware(SecurityMiddleware, settings=settings)
    return TestClient(app)


def authorization(username="healthgrid", password=PASSWORD):
    return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()


def test_shared_access_gate_rejects_missing_wrong_and_malformed_credentials():
    with guarded(security_password=PASSWORD) as client:
        for header in ["", authorization(password="wrong"), "Basic !!!", "Bearer anything"]:
            response = client.get("/private", headers={"Authorization": header})
            assert response.status_code == 401
            assert response.headers["www-authenticate"].startswith("Basic ")
            assert response.headers["cache-control"] == "no-store"
        assert client.get("/private", headers={"Authorization": authorization()}).status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_environment": "production"},
        {"security_password": "short"},
        {"app_environment": "production", "security_password": PASSWORD},
        {
            "app_environment": "production",
            "security_password": PASSWORD,
            "security_allowed_origins": ["https://healthgrid.example"],
            "demo_scenario": "beirut",
        },
        {
            "app_environment": "production",
            "security_password": PASSWORD,
            "security_allowed_origins": ["https://healthgrid.example"],
            "security_allowed_hosts": ["*"],
        },
    ],
)
def test_production_fails_closed_on_unsafe_configuration(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_host_and_cross_site_write_protection():
    with guarded() as client:
        assert client.get("/private", headers={"Host": "attacker.example"}).status_code == 400
        for headers in [
            {"Origin": "https://attacker.example"},
            {"Origin": "null"},
            {"Sec-Fetch-Site": "cross-site"},
        ]:
            assert client.post("/echo", json={}, headers=headers).status_code == 403
        assert (
            client.post(
                "/echo", json={"valid": True}, headers={"Origin": "http://localhost:3000"}
            ).status_code
            == 200
        )


def test_declared_and_streamed_oversized_requests_and_compressed_bodies():
    with guarded(security_max_body_bytes=1024) as client:
        assert (
            client.post("/echo", content="{}", headers={"Content-Length": "9999999"}).status_code
            == 413
        )
        assert (
            client.post(
                "/echo",
                content=iter([b"x" * 800, b"y" * 800]),
                headers={"Content-Type": "application/json"},
            ).status_code
            == 413
        )
        assert (
            client.post("/echo", json={}, headers={"Content-Encoding": "gzip"}).status_code == 415
        )
        assert (
            client.post("/echo", content="{}", headers={"Content-Length": "9" * 5000}).status_code
            == 400
        )


def test_malformed_deep_and_large_collection_json_never_reaches_handler(client):
    response = client.post(
        "/api/v1/facilities/DEMO-A/observations",
        content="secret invalid {",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "secret invalid" not in response.text
    with guarded() as client:
        assert (
            client.post(
                "/echo",
                content="[" * 25 + "0" + "]" * 25,
                headers={"Content-Type": "application/json"},
            ).status_code
            == 413
        )
        assert client.post("/echo", json=list(range(1001))).status_code == 413
        assert (
            client.post(
                "/echo", content='{"quantity":NaN}', headers={"Content-Type": "application/json"}
            ).status_code
            == 413
        )


def test_rate_limit_does_not_trust_forwarded_addresses():
    with guarded(security_requests_per_minute=2) as client:
        assert client.get("/private").status_code == 200
        assert client.get("/private", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 200
        response = client.get("/private", headers={"X-Forwarded-For": "5.6.7.8"})
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"


def test_global_expensive_quota_and_write_quota():
    with guarded(security_expensive_per_minute=1) as client:
        assert client.post("/api/v1/allocation/runs", json={}).status_code == 200
        assert client.post("/api/v1/allocation/runs", json={}).status_code == 429
        assert client.get("/private").status_code == 200
    with guarded(security_writes_per_minute=1) as client:
        assert client.post("/echo", json={}).status_code == 200
        assert client.post("/echo", json={}).status_code == 429


def test_global_cost_quota_survives_peer_cache_churn():
    limits = AdmissionLimits()
    assert limits.allow(("global", "expensive"), 1)
    for index in range(3000):
        assert limits.allow((f"peer-{index}", "all"), 1)
    assert len(limits.buckets) == 2048
    assert not limits.allow(("global", "expensive"), 1)


def test_slow_body_and_expensive_concurrency_admission():
    async def run():
        started, release = asyncio.Event(), asyncio.Event()

        async def handler(scope, receive, send):
            await receive()
            started.set()
            await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})

        settings = Settings(
            _env_file=None, security_max_expensive_concurrent=1, security_body_timeout_seconds=0.02
        )
        middleware = SecurityMiddleware(handler, settings)
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/allocation/runs",
            "headers": [(b"content-type", b"application/json")],
            "client": ("test", 1),
        }

        async def receive():
            return {"type": "http.request", "body": b"{}", "more_body": False}

        first = []

        async def send_first(message):
            first.append(message)

        task = asyncio.create_task(middleware(scope, receive, send_first))
        await started.wait()
        second = []

        async def send_second(message):
            second.append(message)

        await middleware(scope, receive, send_second)
        assert second[0]["status"] == 503
        release.set()
        await task
        assert first[0]["status"] == 200
        assert middleware.limits.inflight == 0

        async def slow_receive():
            await asyncio.sleep(1)

        second.clear()
        await middleware(scope, slow_receive, send_second)
        assert second[0]["status"] == 408
        assert middleware.limits.inflight == 0

    asyncio.run(run())


def test_response_headers_and_injection_identifier_does_not_select_other_hospitals(client):
    response = client.get("/api/v1/facilities")
    assert response.status_code == 200
    for header, expected in [("x-content-type-options", "nosniff"), ("x-frame-options", "DENY")]:
        assert response.headers[header] == expected
    before = response.json()
    attack = quote("DEMO-B' OR 1=1 --", safe="")
    assert client.get(f"/api/v1/facilities/{attack}/snapshot").status_code in {404, 422}
    assert client.get("/api/v1/facilities").json() == before


def test_solver_input_collections_and_numeric_overflow_are_rejected():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "contracts/examples"
    allocation = json.loads((root / "feature-6/improved.request.json").read_text())
    allocation["budget_minor_units"] = 2**100
    with pytest.raises(ValidationError):
        AllocationRunRequest.model_validate(allocation)
    # A malformed giant project list is rejected before constructing a model/solve.
    with pytest.raises(ValidationError):
        InvestmentRunRequest.model_validate({"candidates": [{}] * 101})


def test_extreme_observation_cannot_poison_capacity_or_write_a_report(client):
    before = client.get("/api/v1/facilities/DEMO-B/snapshot").json()
    response = client.post(
        "/api/v1/facilities/DEMO-B/observations",
        json={
            "resource_id": "working-monitors",
            "unit": "item",
            "available_quantity": 1e308,
            "observed_at": "2026-10-10T08:00:00Z",
        },
    )
    assert response.status_code == 422
    assert client.get("/api/v1/facilities/DEMO-B/snapshot").json() == before
