"""Allocation error envelope: the shared shape with allocation-owned codes."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.modules.allocation.schemas import AllocationErrorCode
from app.modules.facilities.schemas import ContractModel, FieldError

MESSAGES = {
    "invalid_request": "The allocation request is invalid.",
    "simulation_run_not_found": "The simulation run was not found.",
    "allocation_run_not_found": "The allocation run was not found.",
}
STATUS = {"invalid_request": 422, "simulation_run_not_found": 404,
          "allocation_run_not_found": 404}


class AllocationErrorDetail(ContractModel):
    code: AllocationErrorCode
    message: str
    fields: list[FieldError]


class AllocationErrorResponse(ContractModel):
    error: AllocationErrorDetail


class AllocationError(Exception):
    def __init__(self, code: str, fields: list[FieldError] | None = None):
        self.code = code
        self.fields = fields or []


def error_response(error: AllocationError) -> JSONResponse:
    body = AllocationErrorResponse(error=AllocationErrorDetail(
        code=error.code, message=MESSAGES[error.code], fields=error.fields))
    return JSONResponse(status_code=STATUS[error.code], content=body.model_dump(mode="json"))


class AllocationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def contract_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except AllocationError as exc:
                return error_response(exc)
            except RequestValidationError as exc:
                fields = [
                    FieldError(field=".".join(map(str, issue["loc"][1:])),
                               message=issue["msg"].removeprefix("Value error, "))
                    for issue in exc.errors()
                ]
                return error_response(AllocationError("invalid_request", fields))

        return contract_handler
