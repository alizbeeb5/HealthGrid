"""Provider diagnostics explain recovery without leaking provider payloads."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openai import APIConnectionError, APIStatusError

from app.modules.intelligence.advice_schemas import EmergencyAdviceRequest
from app.modules.intelligence.config import IntelligenceSettings
from app.modules.intelligence.emergency import emergency_advice
from app.modules.intelligence.failures import failure_warning


@pytest.mark.parametrize(
    "status,code,expected",
    [
        (400, "invalid_json_schema", "request configuration"),
        (401, "invalid_api_key", "server API key"),
        (403, None, "project access"),
        (404, None, "configured model"),
        (429, "insufficient_quota", "billing"),
        (429, None, "rate-limited"),
        (500, None, "server error"),
    ],
)
def test_provider_error_categories_do_not_expose_raw_content(status, code, expected):
    response = SimpleNamespace(status_code=status, headers={}, request=SimpleNamespace())
    error = APIStatusError(
        "private report and secret key",
        response=response,
        body={"code": code, "message": "private report and secret key"},
    )
    warning = failure_warning(error, "provider")
    assert expected in warning
    assert "private report" not in warning and "secret key" not in warning


@pytest.mark.parametrize(
    "error,stage,expected",
    [
        (TimeoutError("private report"), "provider", "timeout"),
        (ValueError("private report"), "evidence", "unsupported hospital"),
        (ValueError("private report"), "schema", "required incident or guidance format"),
        (RuntimeError("private report"), "provider", "unexpectedly"),
        (
            APIConnectionError(request=SimpleNamespace()),
            "provider",
            "network connection",
        ),
    ],
)
def test_local_failure_categories_are_safe(error, stage, expected):
    assert expected in failure_warning(error, stage)
    assert "private report" not in failure_warning(error, stage)


def test_guidance_returns_timeout_detail_and_preserves_manual_input():
    request = EmergencyAdviceRequest(
        incident={
            "title": "Fictional report",
            "report_text": "Fictional outage",
            "service_id": None,
            "starts_at": None,
            "expected_ends_at": None,
            "affected_facility_ids": [],
            "service_overrides": [],
            "resource_overrides": [],
            "assumptions": [],
        }
    )
    before = request.model_dump()
    provider = SimpleNamespace(advise=AsyncMock(side_effect=TimeoutError("private report")))
    response = asyncio.run(
        emergency_advice(
            request,
            {},
            IntelligenceSettings(_env_file=None, openai_api_key="fictional-key"),
            datetime(2026, 10, 10, tzinfo=UTC),
            provider,
        )
    )
    assert response.advice_status == "failed" and response.proposal is None
    assert "timeout" in response.warnings[-1]
    assert "private report" not in response.model_dump_json()
    assert request.model_dump() == before
