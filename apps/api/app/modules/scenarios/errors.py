"""Scenario error envelope (same shape as Feature 1, scenarios-owned codes)."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.modules.facilities.schemas import FieldError
from app.modules.scenarios.schemas import ScenarioErrorDetail, ScenarioErrorResponse

MESSAGES = {
    "invalid_request": "The request is invalid.",
    "incident_not_found": "The incident was not found.",
    "revision_not_found": "The incident revision was not found.",
    "run_not_found": "The simulation run was not found.",
    "revision_conflict": "This incident has already been confirmed.",
    "incident_not_confirmed": "Only a confirmed revision can be simulated.",
}
STATUS = {
    "invalid_request": 422,
    "incident_not_found": 404,
    "revision_not_found": 404,
    "run_not_found": 404,
    "revision_conflict": 409,
    "incident_not_confirmed": 409,
}


class ScenarioError(Exception):
    def __init__(
        self,
        code: str,
        fields: list[FieldError] | None = None,
        existing_revision_id: str | None = None,
    ):
        self.code = code
        self.fields = fields or []
        self.existing_revision_id = existing_revision_id


def error_response(error: ScenarioError) -> JSONResponse:
    body = ScenarioErrorResponse(
        error=ScenarioErrorDetail(
            code=error.code,
            message=MESSAGES[error.code],
            fields=error.fields,
            existing_revision_id=error.existing_revision_id,
        )
    )
    return JSONResponse(status_code=STATUS[error.code], content=body.model_dump(mode="json"))


def _fields(exc: RequestValidationError) -> list[FieldError]:
    """Payload-key paths such as input.resource_overrides.0.unit; body root -> ''."""
    fields = []
    for issue in exc.errors():
        _source, *path = issue["loc"]
        message = issue["msg"].removeprefix("Value error, ")
        fields.append(FieldError(field=".".join(map(str, path)), message=message))
    return fields


class ScenarioRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def contract_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except ScenarioError as exc:
                return error_response(exc)
            except RequestValidationError as exc:
                return error_response(ScenarioError("invalid_request", _fields(exc)))

        return contract_handler
