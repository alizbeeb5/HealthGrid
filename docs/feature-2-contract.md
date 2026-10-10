# Feature 2: Current capacity and bottlenecks

Status: the backend schemas and endpoint are implemented and included in
`contracts/openapi.json`. The endpoint returns HTTP 500 until the capacity engine
(`engines/capacity.py`) and the runtime profile
`data/synthetic/feature-2/service-requirements.json` (one profile object, or a
list of them) are merged. Keep the existing stack and Feature 1 wire names.

## User outcome

Open a hospital and see, for each configured service, the estimated number of
simultaneous service places its reported resources can support, the limiting
resources, and the evidence behind the estimate. Save a resource observation in
Feature 1, refresh capacity, and see the estimate change.

This is the foundation for future predictions, incident simulations, response
allocation and funding comparisons. Those features are later milestones.

The first profile models emergency care with fictional requirements. It is a
resource-based estimate, not a clinically validated capacity, spare admission
capacity, patients per day, or an authorization to transfer patients. Existing
data does not describe all occupied/committed resources or clinical constraints.
Show that limitation alongside the result. Requirements are configurable by
service; do not hard-code the example into the engine or frontend.

## Calculation agreement

For each required resource:

`capacity_limit = floor(available_quantity / required_per_capacity_unit)`

When all inputs are usable:

`estimated_capacity = min(capacity_limit)`

Return every tied limiting resource in `bottleneck_resource_ids`. Use exact
decimal arithmetic from serialized numeric values before flooring to avoid
floating-point undercounts. Requirements must be finite and strictly positive.

The synthetic profile uses 1 bed, 0.5 nurses and 1 monitor per simultaneous place.
These numbers are demo assumptions, not clinical staffing standards. Oxygen
stock remains visible in the snapshot but is excluded from this profile because
consumption and time assumptions are not yet modeled. No arbitrary conversion
between liters, people, beds or daily throughput is allowed.

Use this precedence for each service:

1. `unavailable` service: result status `unavailable`, estimate 0. This reflects
   the recorded service status, not proof that the resource reports are current.
2. No requirement profile: status `not_configured`, estimate null.
3. `limited` service: status `unknown`, estimate null; the restriction is not
   quantified by current data. Never assume limited means 50% capacity.
4. Any required observation missing or stale: status `unknown`, estimate null.
5. Otherwise: status `calculated`, estimate the minimum, including a valid zero.

Resource limits can still be shown for current observations when the overall
result is unknown. Unknown/stale resource limits are null. Only a calculated
result has bottleneck IDs; other statuses return an empty list. Sort those IDs.
Data freshness uses Feature 1's policy and the same snapshot `as_of`.

Validate profiles before serving requests: unique service IDs, nonempty unique
requirements, known resource IDs, matching catalog units, positive finite ratios,
and an explicit profile version. Invalid configuration must fail visibly; never
silently skip a requirement. Resources absent from a facility snapshot are unknown.

All estimates use `calculation_scope: single_service`: evaluate each service in
isolation using facility-wide observations. Never sum these estimates across
services sharing staff or equipment. Resource conservation belongs to allocation.

## Shared interface: all three teammates use this

API: `GET /api/v1/capacity/facilities/{facility_id}`. No new write endpoint or
database table in this milestone. Resource updates continue through Feature 1.

Response model: `FacilityCapacityResponse`.

| Field | Type / meaning |
| --- | --- |
| `facility_id` | Existing string ID |
| `as_of` | UTC timestamp from the input snapshot |
| `stale_after_hours` | Positive integer; Feature 1 policy |
| `calculation_scope` | Literal `single_service` |
| `services` | List of `ServiceCapacityResult`, ordered by `service_id` |

`ServiceCapacityResult`:

| Field | Type / meaning |
| --- | --- |
| `service_id` | Existing service ID |
| `service_status` | Existing `operating / limited / unavailable` |
| `profile_version` | String, or null when no profile exists |
| `capacity_unit` | Literal `simultaneous_service_place` |
| `status` | `calculated / unknown / unavailable / not_configured` |
| `estimated_capacity` | Nonnegative integer or null; never missing |
| `bottleneck_resource_ids` | List of resource IDs |
| `resource_limits` | List of `ResourceCapacityLimit`, ordered by `resource_id` |
| `reason_codes` | Sorted unique machine-readable strings below |

`ResourceCapacityLimit`: `resource_id` (string), `unit` (existing resource unit),
`required_per_capacity_unit` (positive number), `available_quantity` (nonnegative
number or null), `capacity_limit` (nonnegative integer or null), `data_status`
(Feature 1 enum), `observation_id` (string or null), `observed_at` (UTC or null).
Copy provenance and quantities from the snapshot; do not manufacture observations.
For a missing resource, use the profile's unit and null quantity/provenance.

Reason codes: `service_unavailable`, `requirements_not_configured`,
`service_restriction_unquantified`, `missing_required_observation`,
`stale_required_observation`. Include all applicable codes, not just the one that
determined status. No profile means resource_limits is empty. A fresh calculated
result has an empty reason_codes list.

Profile model: `ServiceRequirement` with `service_id`, `profile_version`,
`capacity_unit`, `requirements`. Each requirement has `resource_id`, `unit`,
`required_per_capacity_unit`. See the example JSON in contracts/examples/feature-2.

Backend-owned Pydantic definitions live in
`apps/api/app/modules/capacity/schemas.py`, with extra fields forbidden. Reuse
Feature 1 identifiers, quantity constraints, units and statuses. Frontend uses
generated API types, never a separately maintained competing interface.

Pure engine interface:

```python
calculate_service_capacity(
    snapshot: FacilitySnapshotResponse,
    service: FacilityService,
    requirement: ServiceRequirement | None,
) -> ServiceCapacityResult
```

The API service obtains one snapshot through `facilities.service.get_snapshot`,
then passes its services and matching profiles to the engine. No cross-module
repository access. The engine has no database, HTTP, system clock or AI calls.
The supplied service must belong to the snapshot; a supplied profile must match
its service ID. Reject programmer errors rather than return a plausible result.

Unknown facility: HTTP 404 using Feature 1's `facility_not_found` error envelope.
An existing facility with zero services returns 200 and `services: []`.
Unknown capacity is a successful result, not an HTTP error. Configuration failures
are server errors, never successful zero estimates.

## Three assignments

### Teammate 1 — Frontend: capacity panel

Own apps/web only. Add a capacity panel to the existing hospital details view:
estimate/unit, service status, limiting resources, per-resource calculation,
source timestamps, synthetic assumptions and the single-service limitation.
Display clear loading, request-error, unknown, unavailable and not-configured
states. Keep null distinct from zero. Label the number “Modeled service places”.
Use example responses until the endpoint exists. After a saved observation,
refetch both snapshot and capacity; mark the old capacity as updating and prevent
an older request from overwriting a newer result. Show capacity's own as_of.

Done: Demo B shows 5 and monitors as the bottleneck; after monitors change to 8,
it shows 8. Missing/stale data explains why capacity cannot be determined.

### Teammate 2 — Backend: contract and endpoint

Own modules/capacity schemas, router and service; OpenAPI export. Implement the
types above first, validate example payloads, then connect the existing snapshot
service to the engine and validated demo profile. Return provenance and statuses
unchanged. Register the GET route under the existing capacity router. No new
migration is needed. Ensure profile data is included wherever the API is packaged.

Done: endpoint matches examples at the frozen fixture clock, returns the standard
404, handles a facility with no services, and reflects saved observations without
altering history. Test at least one real snapshot-to-engine integration.

### Teammate 3 — Data/calculation: engine and demo rules

Own engines/capacity.py, data/synthetic/feature-2 and focused engine tests. Copy
the agreed profile to a runtime data file; keep it identical to the contract
example. Implement formula, validation, status precedence and tied bottlenecks.
Prepare expected cases: normal, zero, missing, stale, tied limits, fractional
ratio, limited/unavailable service, absent profile and invalid configuration.
Use the existing Feature 1 snapshots at 2026-10-10T09:00:00Z for demo examples.

Done: Demo B computes min(18, 18, 5) = 5; changing monitors to 8 produces 8;
Demo A is unknown; Demo C is unavailable/0 with stale-input reasons retained.
Non-required oxygen does not affect this particular profile. Tests also verify
that observations are not modified and invalid ratios/units are rejected.

## Handoff and merge agreement

1. All three review this contract and examples. Teammate 2 publishes Pydantic
   schemas plus regenerated OpenAPI first; teammate 1 generates frontend types.
2. Work on separate branches: feature-2/frontend, feature-2/api,
   feature-2/capacity-engine. Each teammate owns only the files listed above.
3. Teammate 2 owns contract/example edits; teammate 3 proposes numerical changes
   through that owner. No unilateral field renaming. Update schema, examples,
   generated types and consumers together if a change is necessary.
4. Merge engine, endpoint, then frontend integration. Frontend can build against
   fixtures while the other tasks proceed. Use a frozen clock for fixtures;
   real runtime freshness uses request time and may mark old demo data stale.
5. Joint finish: current Demo B snapshot -> capacity 5 -> save monitors 8 ->
   capacity 8 -> refresh and see the same result. The user handles browser checks;
   teammates run focused engine/API checks and frontend typechecking.

OpenAI emergency interpretation remains a later feature: it will produce incident
assumptions that feed this deterministic calculation and subsequent allocation.
This milestone has no model calls and makes no forecast or dispatch decision.
