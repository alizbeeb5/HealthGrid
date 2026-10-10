"""Generate planned Feature 1 OpenAPI without exposing unimplemented endpoints."""

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from pydantic.json_schema import models_json_schema  # noqa: E402

from app.modules.facilities.schemas import (  # noqa: E402
    ErrorResponse,
    FacilityListResponse,
    FacilitySnapshotResponse,
    ObservationCreate,
    ObservationResponse,
    ResourceDefinition,
)

models = [
    FacilityListResponse,
    FacilitySnapshotResponse,
    ObservationCreate,
    ObservationResponse,
    ErrorResponse,
    ResourceDefinition,
]
_, definitions = models_json_schema(
    [(model, "validation") for model in models],
    ref_template="#/components/schemas/{model}",
)


def response(model: str, description: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{model}"}}},
    }


facility_id = {
    "name": "facility_id",
    "in": "path",
    "required": True,
    "schema": {"type": "string", "minLength": 1, "maxLength": 64},
}
errors = {
    "404": response("ErrorResponse", "Facility does not exist"),
    "422": response("ErrorResponse", "Invalid request or observation"),
}
schema = {
    "openapi": "3.1.0",
    "info": {
        "title": "HealthGrid Feature 1 — Planned Contract",
        "version": "1.0.0",
        "description": "Shared interface for implementation; these endpoints are not live yet.",
    },
    "paths": {
        "/api/v1/facilities": {
            "get": {
                "operationId": "list_facilities",
                "responses": {"200": response("FacilityListResponse", "Facility list")},
            },
        },
        "/api/v1/facilities/{facility_id}/snapshot": {
            "get": {
                "operationId": "get_facility_snapshot",
                "parameters": [facility_id],
                "responses": {
                    "200": response("FacilitySnapshotResponse", "Current resource observations"),
                    **errors,
                },
            },
        },
        "/api/v1/facilities/{facility_id}/observations": {
            "post": {
                "operationId": "create_resource_observation",
                "parameters": [facility_id],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ObservationCreate"},
                        },
                    },
                },
                "responses": {
                    "201": response("ObservationResponse", "New observation stored"),
                    **errors,
                },
            },
        },
    },
    "components": {"schemas": definitions["$defs"]},
}
output = API_ROOT.parents[1] / "contracts" / "feature-1.openapi.json"
output.write_text(json.dumps(schema, indent=2) + "\n")
print(f"Exported planned contract: {output}")
