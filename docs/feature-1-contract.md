# Feature 1: shared implementation contract, v1

This is the active feature for all three teammates. Implement only the hospital
operational snapshot and resource updates before moving to capacity calculations.
The three endpoints below are live in the backend and included in
`contracts/openapi.json`. Product scope remains in product-scope.md.

## One source of truth

`apps/api/app/modules/facilities/schemas.py` defines payload fields and types.
`contracts/feature-1.openapi.json` is generated from those schemas plus the three
planned endpoint definitions in `apps/api/scripts/export_feature_1_contract.py`.
Frontend types are generated into `apps/web/src/lib/api/feature-1-schema.d.ts`;
use the aliases in `feature-1.ts`. Do not maintain separate handwritten interfaces.

Once endpoints are implemented, the backend owner must make their live schemas
match this contract and consolidate it into the regular OpenAPI export. Until
then, keep the planned contract separate from `contracts/openapi.json` so the
live API does not falsely advertise features that do not work.

## Naming and types

- Use `facility`, not `hospital`, in code, API paths, database names and fixtures.
  The UI can display the word Hospital.
- Use snake_case for JSON fields and database columns: `facility_id`,
  `resource_id`, `available_quantity`, `observed_at`. Frontend domain objects keep
  these exact keys; local functions may use camelCase.
- IDs are opaque strings, 1-64 characters; letters, digits, hyphens and underscores.
  Never use a display name as a key. Keep existing fixture IDs DEMO-A/B/C.
- JSON quantities are finite numbers, never numeric strings, booleans or NaN.
- Timestamps are timezone-aware ISO 8601. Send and return UTC with Z; convert
  user-entered local times before sending. The server normalizes offset inputs.
- Required nullable fields stay present with `null`; do not omit them.
- Availability zero means known zero. Null means no observation exists.

## Canonical entities

| Entity | Exact fields |
| --- | --- |
| Facility | facility_id, name, latitude, longitude, last_reported_at |
| FacilityService | facility_id, service_id, name, status |
| ResourceDefinition | resource_id, name, category, unit, allows_fractional |
| ObservationCreate | resource_id, available_quantity, unit, observed_at |
| ObservationResponse | all ObservationCreate fields plus observation_id, facility_id, recorded_at |
| ResourceSnapshot | all ResourceDefinition fields plus observation_id, available_quantity, observed_at, recorded_at, data_status |
| FacilitySnapshotResponse | facility, services, resources, as_of, stale_after_hours |

`service_id` identifies a service type; status belongs to the pair
(facility_id, service_id). Resource observations are facility-wide; do not duplicate
one shared inventory into each service. Service-resource requirements come later.
The backend tracks which resource definitions are applicable to each facility so
an unreported applicable resource can appear as unknown in its snapshot.

## Exact enums

- Service status: `operating`, `limited`, `unavailable`.
- Resource category: `beds`, `staff`, `equipment`, `supplies`, `infrastructure`.
- Initial units: `bed`, `person`, `item`, `liter`.
- Data status: `current`, `stale`, `unknown`.

Extend units deliberately through this contract. Staff person-count is a snapshot,
not staff-hours or a qualified service-capacity estimate. Physical beds are not
usable service capacity. Oxygen values are illustrative inventory volumes, not
clinical consumption rules.

## Endpoints and payloads

| Method and path | Request | Success |
| --- | --- | --- |
| GET /api/v1/facilities | No body | 200 FacilityListResponse: {items: Facility[]} |
| GET /api/v1/facilities/{facility_id}/snapshot | No body | 200 FacilitySnapshotResponse |
| POST /api/v1/facilities/{facility_id}/observations | ObservationCreate | 201 ObservationResponse |

The facility ID comes from the URL; do not repeat it in the update body. The server
assigns observation_id and recorded_at. IDs and resource definitions are seeded
for this feature; facility creation and service-status editing are outside it.

Example request to POST /api/v1/facilities/DEMO-A/observations:

```json
{
  "resource_id": "available-beds",
  "available_quantity": 10,
  "unit": "bed",
  "observed_at": "2026-10-10T08:55:00Z"
}
```

Complete matching list, snapshot, update and error examples live in
`contracts/examples/feature-1/`. All are synthetic. They use a fixed as_of time;
mock freshness must be evaluated against that time, not today's clock.

## Update and snapshot semantics

- Each successful POST appends an observation; never overwrite history.
- Select the latest observation per (facility_id, resource_id) by observed_at,
  then recorded_at, then observation_id for deterministic ties.
- Accept valid older reports as history; they do not replace newer observations.
- recorded_at is the server receipt time. facility.last_reported_at is the latest
  receipt time for any observation, not proof all resource reports are current.
- Snapshot as_of is server time. Initial stale_after_hours is 24, returned by the
  backend. It is a demo policy, not a clinically validated reporting interval.
- No observation: quantity, observation_id, observed_at and recorded_at are null;
  data_status is unknown. Do not turn it into zero.
- With an observation: those fields are populated. If as_of - observed_at is
  greater than 24 hours, status is stale; otherwise current. Zero can be current.
- Order facilities by facility_id, services by service_id and resources by
  resource_id for stable fixtures and UI results.
- After saving, frontend refetches the snapshot. It must not assume a newly
  submitted historical observation becomes the latest displayed value.
- Version 1 has no idempotency key. Disable repeated submission while pending;
  do not automatically retry POST after an ambiguous network failure.

## Validation and errors

Pydantic handles payload shape, IDs, supported enum values, nonnegative finite
quantities, timezone-aware timestamps and unexpected fields. Service validation
must additionally enforce:

- Facility exists and resource is known and applicable to that facility.
- Submitted unit equals the resource's configured unit; no automatic conversion.
- Whole numbers for resources whose allows_fractional is false.
- observed_at is no more than five minutes ahead of server time (clock-skew
  tolerance). Old observations are allowed.

Use 404 for an unknown facility. Use 422 for invalid fields, an unknown/inapplicable
resource, a unit mismatch or invalid time. Error shape is always:

```json
{
  "error": {
    "code": "invalid_observation",
    "message": "The observation could not be saved.",
    "fields": [
      {"field": "unit", "message": "Expected bed for resource available-beds."}
    ]
  }
}
```

Allowed codes: facility_not_found, invalid_observation, invalid_request.
The backend owner must add a request-validation exception handler for these
endpoints so FastAPI's default 422 envelope also follows this shape. Do not change
other APIs accidentally. Field paths use the payload keys; non-field errors use an
empty fields list. Network/5xx failures get a general retry message in the UI.

## Exact responsibilities for this feature

1. Frontend owner: hospital list/details, resource update form and typed client.
   Consume generated types and JSON fixtures; coordinate no field renaming alone.
2. Backend owner: models/migrations, repositories, three endpoints, snapshot
   selection, persistence and consistent error mapping. Own shared schemas.
3. Data/validation owner: extend shared fixtures, implement catalog-aware validation
   in ingestion/validation.py, and test input/boundary cases. The backend imports
   this validation rather than copying it. Coordinate schema edits with backend.

The data/validation owner supplies validation as a pure function accepting the
ObservationCreate, matching ResourceDefinition and an explicit server time. The
backend resolves facility/resource existence and applicability first. The function
returns FieldError entries (empty means valid); routers map these to ErrorResponse.
Use this exact function boundary:

```python
validate_observation(
    observation: ObservationCreate,
    resource: ResourceDefinition,
    now: datetime,
) -> list[FieldError]
```

The frontend client exports `listFacilities()`, `getFacilitySnapshot(facility_id)`
and `createResourceObservation(facility_id, payload)` with the generated response
and request types. These are agreed function names for implementation, not
already implemented functions.

This allows the third teammate to work without the database.

## Contract change and checks

Discuss a field change together -> update Python schemas/endpoint definition ->
update fixtures -> export OpenAPI -> regenerate TypeScript -> run checks.

```bash
python apps/api/scripts/export_feature_1_contract.py
python apps/api/scripts/check_feature_1_examples.py
npm run generate:feature-1 --prefix apps/web
npm run typecheck --prefix apps/web
```

Do not edit generated files manually. The first integration checkpoint is:
list -> open DEMO-A -> submit valid observation -> refetch -> refresh browser ->
value persists, timestamps are shown and old observations remain in the database.
