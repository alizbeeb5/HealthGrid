"""HealthGrid API entry point. Business modules are scaffolds until implemented."""

from typing import Literal

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import get_settings
from app.core.security import SecurityMiddleware
from app.routes import router

settings = get_settings()
production = settings.app_environment == "production"
app = FastAPI(
    title="HealthGrid API",
    version="0.1.0",
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
)
app.include_router(router, prefix="/api/v1")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.security_allowed_hosts)
app.add_middleware(SecurityMiddleware, settings=settings)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request, error):
    # Do not echo reports, credentials or untrusted input in framework errors.
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "invalid_request",
                "message": "The request is invalid.",
                "fields": [
                    {"field": ".".join(map(str, issue["loc"][1:])), "message": issue["msg"]}
                    for issue in error.errors()
                ],
            }
        },
    )


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["healthgrid-api"] = "healthgrid-api"


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Process liveness only; does not assert database or AI availability."""
    return HealthResponse()
