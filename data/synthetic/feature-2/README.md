# Fictional capacity requirements

`service-requirement.json` is the runtime copy of
`contracts/examples/feature-2/service-requirement.json`. Keep the two files
identical; schema and contract example changes belong to teammate 2.

This manually authored `demo-v1` profile is synthetic: one bed, 0.5 nurses and
one monitor per simultaneous emergency-care place. These are not clinical
staffing standards. Oxygen is excluded because no consumption/time assumption
has been agreed. Estimates are not confirmed spare admission capacity.

## Backend integration

1. Package this JSON with the API deployment and resolve its path explicitly.
2. Parse it using the backend-owned `ServiceRequirement` model.
3. Before serving requests, call `validate_requirement_profiles(profiles, catalog)`
   from `app.engines.capacity` with all profiles and the complete resource catalog.
   Do not catch configuration failures and return zero or omit a requirement.
4. Obtain one Feature 1 snapshot and pass each of its services and its matching
   profile (or None) to `calculate_service_capacity(snapshot, service, requirement)`.
5. Wrap results in the backend's facility response, ordered by service ID; use
   the original snapshot's `as_of` and `stale_after_hours` unchanged.

The engine has no file loading, implicit clock, database, HTTP or AI calls. It
uses the snapshot's Feature 1 data statuses. Missing required resources are
unknown; stale reported values and provenance remain visible but have no limit.
The backend remains responsible for generating freshness at the snapshot clock.
All results are single-service estimates; never add estimates across services
sharing resources. Startup validation checks the complete catalog, not just a
facility's observed resources.

## Expected results and checks

At the frozen Feature 1 clock `2026-10-10T09:00:00Z`:

- Demo B: limits 18 beds, 18 nurse-supported places, 5 monitors; estimate 5.
  A current monitor observation of 8 changes the estimate to 8.
- Demo A: unknown, because the service is limited and monitors are unreported.
- Demo C: unavailable/0, retaining the stale-observation reason.
- A current zero gives calculated/0; all tied minimum resource IDs are returned.

The focused tests are `apps/api/tests/test_capacity_engine.py`. They require
teammate 2's published capacity schemas, including `ServiceRequirement`,
`ResourceCapacityLimit` and `ServiceCapacityResult`. From the repository root:

```bash
PYTHONPATH=apps/api .venv/bin/python -m unittest discover -s apps/api/tests -p 'test_capacity_engine.py' -v
```

Tests cover shared results, monitor updates, zero, missing/stale inputs, tied
limits, exact decimal ratios, status precedence, invalid configuration, source
provenance and input immutability. The browser/API persistence checkpoint remains
an integration task; engine tests do not prove a saved observation persists.
