"""HealthGrid API entry point. Business modules are scaffolds until implemented."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.modules import router

app = FastAPI(title="HealthGrid API", version="0.1.0")
app.include_router(router, prefix="/api/v1")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["healthgrid-api"] = "healthgrid-api"


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Process liveness only; does not assert database or AI availability."""
    return HealthResponse()
