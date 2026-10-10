"""Feature 1 error envelope, applied only to routes on the facilities router."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.modules.facilities.schemas import ErrorDetail, ErrorResponse, FieldError


class FacilityNotFound(Exception):
    def __init__(self, facility_id: str):
        self.facility_id = facility_id


class ObservationRejected(Exception):
    def __init__(self, fields: list[FieldError]):
        self.fields = fields


def error_response(status_code: int, code: str, message: str, fields: list[FieldError]):
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, fields=fields))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _request_fields(exc: RequestValidationError) -> tuple[bool, list[FieldError]]:
    """Map FastAPI errors to payload keys; report whether any came from the body."""
    in_body = False
    fields: list[FieldError] = []
    for issue in exc.errors():
        source, *path = issue["loc"]
        in_body = in_body or source == "body"
        # A malformed or missing body has no field path: a non-field error.
        if path and not isinstance(path[0], int):
            fields.append(FieldError(field=".".join(map(str, path)), message=issue["msg"]))
    return in_body, fields


class FacilityRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def contract_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except FacilityNotFound as exc:
                return error_response(
                    404, "facility_not_found", f"Facility {exc.facility_id} was not found.", []
                )
            except ObservationRejected as exc:
                return error_response(
                    422, "invalid_observation", "The observation could not be saved.", exc.fields
                )
            except RequestValidationError as exc:
                in_body, fields = _request_fields(exc)
                if in_body:
                    return error_response(
                        422, "invalid_observation", "The observation could not be saved.", fields
                    )
                return error_response(422, "invalid_request", "The request is invalid.", fields)

        return contract_handler
