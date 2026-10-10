# Isolated exercise contract

Authoritative Pydantic types: `app.modules.demo.schemas`. Generated OpenAPI and
frontend API types include these shapes. Examples live in `contracts/examples/demo`.
The exercise orchestrates existing Feature 1–8 contracts; their numerical engines
and saved-run response shapes are unchanged.

## GET /api/v1/demo

Returns `ExerciseContext`. Ordinary mode returns `enabled: false` and empty context.
In explicit Beirut mode, returns `synthetic: true`, phase, UTC exercise clock,
manifest links to saved runs/decisions, resource catalog, fictional facility roles,
saved coverage metrics and typed incident/allocation/investment inputs. Metric
costs use USD minor units; coverage/unmet counts use simultaneous service places
across the three included operating facilities. Recovery cost excludes transfer.
Initial response examples contain generated IDs from an isolated run, not stable
production identifiers. Frontend must follow the returned links and IDs.

The profile and catalog are selected server-side. Client routing never changes
the clock. Load this context before mounting pages; when enabled, use API mode
rather than older browser-only fixtures.

## POST /api/v1/demo/advance

Body: `expected_phase`, `target_phase`. Both are enums. Supported transitions:

| From | To | New UTC clock | Explicit rehearsal effects |
| --- | --- | --- | --- |
| assessment | response | 2020-08-04T17:00:00Z | Rehearse transfer decision events and append separate synthetic reports |
| response | recovery | 2020-08-11T17:05:00Z | Rehearse recovery decision; save review before reports, append reports, save review after reports |

Returns the updated `ExerciseContext`. An already-applied target returns the
current context without duplicate events/reports. A skipped/backward or outdated
transition returns 409. Cancelled/rejected canonical decisions are not overridden.
Controls return 404 outside explicit SQLite exercise mode; unprepared exercise
state returns 503. Validation failures use the app's normal error handling.

The outer SQLite transaction covers every stage effect even though domain services
commit internally; they use savepoints. Failures roll back phase, clock, events,
observations, synthetic follow-up daily history and reviews together. This is local rehearsal behavior with simulated
identities, not a production authentication/approval mechanism.

## Startup and data ownership

The launcher chooses an isolated file before loading application settings, applies
migration 0008, generates history, captures the pre-event baseline and saves real
computed plans plus decision drafts. Then it appends incident reports. It refuses
to seed over an existing non-exercise hospital dataset. `--fresh` makes another
file; it never deletes previous exercise or operational records.

Clock values are shared through the existing `server_now` dependency. Live provider
calls are neither mocked nor invoked by startup/stage controls. The optional
prerecorded interpretation in the UI is labeled synthetic and requires review.

Resume appends missing synthetic complete-day history through the exercise clock’s previous day, including legacy short-history repair. Existing daily rows are never overwritten. Recovery history excludes the funded changes first reported on the evaluation date.
