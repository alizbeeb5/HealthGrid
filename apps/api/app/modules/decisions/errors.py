"""Decision error envelope: the shared shape with decision-owned codes."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.modules.decisions.schemas import DecisionErrorDetail, DecisionErrorResponse
from app.modules.facilities.schemas import FieldError

STATUS = {
    "invalid_request": 422, "source_run_not_found": 404, "decision_not_found": 404,
    "review_not_found": 404, "invalid_transition": 409, "prerequisite_not_met": 409,
    "duplicate_source_decision": 409, "version_conflict": 409, "idempotency_conflict": 409,
}


class DecisionError(Exception):
    def __init__(self, code: str, message: str, fields: list[FieldError] | None = None, *,
                 current_version: int | None = None,
                 existing_decision_id: str | None = None):
        self.code = code
        self.message = message
        self.fields = fields or []
        self.current_version = current_version
        self.existing_decision_id = existing_decision_id


def invalid(field: str, message: str) -> DecisionError:
    return DecisionError("invalid_request", "The decision request is invalid.",
                         [FieldError(field=field, message=message)])


def error_response(error: DecisionError) -> JSONResponse:
    body = DecisionErrorResponse(error=DecisionErrorDetail(
        code=error.code, message=error.message, fields=error.fields,
        current_version=error.current_version,
        existing_decision_id=error.existing_decision_id))
    return JSONResponse(status_code=STATUS[error.code], content=body.model_dump(mode="json"))


class DecisionRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def contract_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except DecisionError as exc:
                return error_response(exc)
            except RequestValidationError as exc:
                fields = [
                    FieldError(field=".".join(map(str, issue["loc"][1:])),
                               message=issue["msg"].removeprefix("Value error, "))
                    for issue in exc.errors()
                ]
                return error_response(DecisionError(
                    "invalid_request", "The decision request is invalid.", fields))

        return contract_handler
