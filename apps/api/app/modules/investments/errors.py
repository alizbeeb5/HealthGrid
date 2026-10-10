"""Investment error envelope: the shared shape with investment-owned codes."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.modules.facilities.schemas import ContractModel, FieldError
from app.modules.investments.schemas import InvestmentErrorCode

MESSAGES = {
    "invalid_request": "The investment request is invalid.",
    "allocation_run_not_found": "The allocation run was not found.",
    "investment_run_not_found": "The investment run was not found.",
}
STATUS = {"invalid_request": 422, "allocation_run_not_found": 404,
          "investment_run_not_found": 404}


class InvestmentErrorDetail(ContractModel):
    code: InvestmentErrorCode
    message: str
    fields: list[FieldError]


class InvestmentErrorResponse(ContractModel):
    error: InvestmentErrorDetail


class InvestmentError(Exception):
    def __init__(self, code: str, fields: list[FieldError] | None = None):
        self.code = code
        self.fields = fields or []


def error_response(error: InvestmentError) -> JSONResponse:
    body = InvestmentErrorResponse(error=InvestmentErrorDetail(
        code=error.code, message=MESSAGES[error.code], fields=error.fields))
    return JSONResponse(status_code=STATUS[error.code], content=body.model_dump(mode="json"))


class InvestmentRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def contract_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except InvestmentError as exc:
                return error_response(exc)
            except RequestValidationError as exc:
                fields = [
                    FieldError(field=".".join(map(str, issue["loc"][1:])),
                               message=issue["msg"].removeprefix("Value error, "))
                    for issue in exc.errors()
                ]
                return error_response(InvestmentError("invalid_request", fields))

        return contract_handler
