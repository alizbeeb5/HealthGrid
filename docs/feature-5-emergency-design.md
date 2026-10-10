# Feature 5: Emergency intake and confirmed incident baseline

Status: design only. No incident endpoints, persistence or model calls are implemented
by this document. Features 1–3 remain the source of reported hospital data.

## Outcome and workflow

From /overview, choose Declare incident. Enter a structured emergency directly,
or paste a situation report and ask AI to propose fields and review categories.
Inspect/edit the proposal, save a draft, then explicitly confirm it. HealthGrid
stores an immutable incident revision and the network baseline used for later
impact simulation. Confirmation means the planner accepted the scenario inputs;
it does not authorize transfers, staff assignments or spending.

Demo: "Demo Hospital B's emergency service is unavailable after a power failure.
The disruption started at 10:00 UTC and is expected to last six hours."
The form identifies DEMO-B/emergency-care, dates and the outage. Missing resource
counts remain unknown. After review, save a confirmed incident and inspect its
baseline: the original capacity and observation IDs are retained. Hospital B's
reported service remains operating until someone separately updates its report.
The incident describes a scenario assumption, not a replacement operational report.

The next feature will apply that overlay and recalculate capacity; a later response
feature will use Google OR-Tools to allocate available resources under constraints.
This milestone finishes at a confirmed, retrievable incident with saved inputs.

## Build now

- Incident form and incident list/details under /scenarios, linked from overview.
- Optional report interpretation with source excerpts and unresolved questions.
- Fast Decisions API assessment of fixed review categories.
- Draft saving, explicit confirmation, immutable revisions and baseline capture.
- Separate AI failure states; manual entry/confirmation continue without AI.

No automatic dispatch, solver, investment comparison or demand forecast here.
No urgency score interpreted as clinical triage. Review flags describe the report,
not the actual severity of patient conditions.

## Model responsibilities and provider agreement

Official documentation checked on 2026-10-10:
https://developers.openai.com/api/docs/guides/decisions
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses

Use Decisions for fixed choices, not arbitrary JSON extraction. The current
documented Decisions model is gpt-6-luna, with POST /v1/decisions; SDK support must
be checked before implementation and requirements/lock updated by the backend owner.
Use Responses with Structured Outputs for extracted fields and evidence. Set a
separately configurable supported Responses model; do not invent a model alias.

Both calls receive the original report plus known facility/service/resource IDs;
they can run concurrently. Each result is independent. A fast assessment can be
shown while extraction is still running. Provider success is not factual validation.
Never promote model output to a confirmed incident without user review.

Fixed review questions, named and versioned as emergency-review-v1:
- outage_reported: yes / no / unclear
- multiple_facilities_reported: yes / no / unclear
- resource_loss_reported: yes / no / unclear
- clarification_needed: yes / no / unclear

These are suggestions shown in the review panel. All incidents get explicit review;
clarification_needed=no never bypasses review. Handle refusal per answer: value
null, answer_status=refused. Record provider model, rubric_version and elapsed_ms.
No latency guarantee or probability threshold is implied. AI cannot choose resource
allocations or calculate capacity. Report text is data, never instructions to tools.

## Shared incident fields

Reuse existing snake_case, Identifier, units and timezone-aware UTC timestamps.
Backend owns Pydantic schemas; frontend generates types from OpenAPI.

IncidentInput (used for draft and confirmation):

| Field | Type / agreement |
| --- | --- |
| title | Nonempty string, max 200 |
| report_text | String or null, max 10,000; original situation report |
| starts_at | UTC timestamp, required for confirmation |
| expected_ends_at | UTC timestamp or null; if supplied, later than starts_at |
| affected_facility_ids | Nonempty sorted unique existing facility IDs |
| service_overrides | List of ServiceOverride |
| resource_overrides | List of ResourceOverride |
| planning_horizon_hours | Positive integer, max 168; default 24 |
| assumptions | List of plain-text user assumptions, each max 500 |

ServiceOverride: facility_id, service_id, status (existing service-status enum),
restriction_note (string/null). A limited service requires a nonempty note, but
remains numerically unknown until its restriction is explicitly modeled.

ResourceOverride: facility_id, resource_id, available_quantity (existing Quantity),
unit (existing ResourceUnit). This is an absolute scenario quantity, not a quantity
to subtract. Zero is explicit zero; omitted resources retain baseline observations.
Do not turn an unknown baseline into known availability without an explicit entry.

All overrides apply at starts_at for the whole planning window in this milestone.
expected_ends_at is contextual metadata; automatic restoration at that time is not
modeled yet. Warn about that assumption before confirmation. Require at least one
override or a nonempty assumptions list. No patients/day versus simultaneous-place
conversion. Demand and transport constraints remain future schema extensions.

Require one override per facility/service or facility/resource pair, existing
service affiliation/resource applicability, matching units and whole quantities
where the resource forbids fractions. Every overridden facility must appear in
affected_facility_ids. No arbitrary service/resource IDs from model output.

Draft inputs may have starts_at null or empty affected_facility_ids while incomplete;
use a separate IncidentDraftInput schema with those two relaxed constraints. The
confirmation schema is IncidentInput. Validate fields that are supplied even in
drafts; a draft is not permission to store invalid units or negative quantities.

## AI proposal contract

AI extraction returns a candidate IncidentDraftInput plus `evidence` entries:
`field_path` (e.g. service_overrides.0.status), `source_excerpt` (literal substring
of report_text). Every proposed non-default extracted value needs evidence or must
remain null/absent with a question. Validate source excerpts as exact substrings;
this checks provenance, not whether the interpretation is correct. Defaults such
as the 24-hour horizon are explicitly labeled policy defaults.

Return `questions` (list of strings), `warnings` (list of strings) and per-component
statuses: assessment_status/extraction_status = completed / unavailable / failed /
refused. Assessment contains the four named choice answers (value and answer_status);
extraction candidate is null on failure/refusal. Responses refusal and incomplete
output are handled separately from valid candidates. The adapter never fabricates
missing values. Ambiguous facility names remain unresolved; let the user select IDs.

Suggested UI uses separate Assess report and Extract fields actions, optionally one
Interpret report button invoking both endpoints concurrently. Each endpoint is
stateless in this milestone and bounded by a 15-second configurable provider timeout
with no automatic retry. Measure actual elapsed time; this is an application timeout,
not an emergency response performance guarantee. Neither call writes hospital data.

## API and persistence agreement

| Endpoint | Request / response |
| --- | --- |
| POST /api/v1/intelligence/incidents/assess | {report_text} -> assessment_status, answers, model, rubric_version, elapsed_ms |
| POST /api/v1/intelligence/incidents/extract | {report_text} -> extraction_status, candidate, evidence, questions, warnings, model, elapsed_ms |
| POST /api/v1/scenarios/incidents | IncidentDraftInput -> IncidentRevision, 201 |
| GET /api/v1/scenarios/incidents | {items: latest IncidentRevision per incident}, newest created_at first, incident_id tie-break |
| GET /api/v1/scenarios/incidents/{incident_id}/revisions/{revision_id} | Saved IncidentRevision |
| POST /api/v1/scenarios/incidents/{incident_id}/confirm | {draft_revision_id, input: IncidentInput, confirmed_by} -> new confirmed IncidentRevision, 201 |

IncidentRevision: incident_id, revision_id, parent_revision_id (null for initial
draft), status (draft/confirmed), input, created_at, confirmed_at (null for draft),
confirmed_by (null for draft), baseline (null for draft).
confirmed_by is a demo display name, not authenticated identity or enforced roles.
Draft creation has no operational approval state. Preserve original report_text
through confirmation; edited structured fields are the planner's accepted values.

Confirmation requires the supplied draft to be the latest unconfirmed revision.
Atomically create a new revision and capture a baseline with baseline_id, captured_at,
facility_snapshots (all participating hospitals from the facility list, ordered by ID),
and requirement_profiles (the validated profile objects used by the baseline).
Snapshots reuse Feature 1 structures with one shared captured_at. Their observation
IDs, quantities and statuses remain frozen even when subsequent reports arrive.
Profile content, not just version labels, must be saved to reproduce later calculations.
Missing/stale baseline observations remain visible; they do not prevent saving a
valid incident, but the confirmation preview shows their warning before saving.
Baseline capture uses the current reports at confirmation, not AI processing time.

Store revisions and baseline in scenarios-owned tables via an Alembic migration;
JSON payloads are acceptable for the demo with schema_version=1 stored alongside
them. Do not alter Feature 1 observation rows. Baseline and revision creation occur
in one database transaction. Enforce one confirmation per draft in persistence;
repeated/concurrent confirmation returns 409 and the existing revision reference.
The frontend must not automatically retry confirmation after an ambiguous failure.
An existing incident cannot be silently reconfirmed against new current data.

Use the same error envelope shape but scenarios-owned code enum: invalid_request
(422 field errors), incident_not_found/revision_not_found (404), revision_conflict
(409). Keep existing Feature 1 error schemas unchanged. Technical persistence or
baseline failures are 500 with no partial revision saved. An unavailable AI provider
returns 200 with component status unavailable; invalid report_text still returns 422.

## Three tasks and ownership

### Teammate 1 — Emergency form and review flow

Own apps/web scenario components, scenarios page, intelligence/scenario API clients
and the overview Declare incident link. Build manual input first, then report
assessment/extraction buttons. Show evidence, questions, edits, policy defaults,
independent loading/failure states and explicit confirmation. Save/reopen drafts
and confirmed details with baseline timestamps and warnings. Cancel/discard stale
AI results after report edits; never overwrite fields the user edited while awaiting
a model response. Confirmation sends the visible reviewed form, not hidden AI data.

Done: enter the outage manually, save/reopen it, confirm it and inspect its baseline;
the same journey works with missing API key. AI proposals remain editable and draft.

### Teammate 2 — Incident contracts, persistence and baseline

Own modules/scenarios schemas/router/service/repository/models, migration, baseline
capture integration, shared error envelopes, fixtures and OpenAPI. Publish schemas
and examples before the other two integrate. Expose public catalog methods through
facility services when needed. Coordinate exact AI response schemas with teammate 3.
Own dependency/settings/lock changes proposed by the AI owner.

Done: drafts persist; confirmation validates IDs/units, snapshots and profiles are
immutable, duplicate confirmations conflict, and injected failure rolls back both
revision and baseline. Reporting updates do not rewrite a confirmed baseline.

### Teammate 3 — Intelligence adapter and bounded evaluation

Own modules/intelligence schemas (as agreed with teammate 2), router/service and
OpenAI adapter; synthetic report cases and focused adapter tests. Implement Decisions
questions and Responses extraction separately. Catalog matching, evidence validation
and all provider failure/refusal paths are required. Use server-side credentials.
Prepare six reports: clear outage, missing dates, ambiguous name, conflicting values,
resource loss with explicit count/unit, and report text containing tool instructions.
Record expected flags/questions and unsupported facts that must not be invented.

Done: contract-valid review results; no invented IDs/quantities; accurate failure
labels; elapsed time recorded. Tests use stubbed provider responses by default;
paid live evaluation runs only when the team deliberately invokes it. No automatic
model calls in startup or ordinary test runs.

## General team agreement and merge order

1. Backend owns wire names and migrations; AI owner proposes interpretation schemas;
   all three review JSON examples. Extra fields are forbidden; nullable is explicit.
2. Branches: feature-4/frontend, feature-4/incidents, feature-4/intelligence. Respect
   ownership and coordinate shared dependencies, router registration and generated files.
3. Publish schemas/examples, build manual draft/confirmation path, integrate the two
   AI adapters, then integrate UI. Generate frontend API types after OpenAPI changes.
4. Focused backend/model-adapter checks only; user performs browser testing. No
   browser tests/builds by the reviewing agent unless explicitly requested.
5. Shared demo finish: overview -> report/manual outage -> review -> draft -> confirm
   -> reload saved baseline -> update hospital report -> verify baseline unchanged.

Feature 5: apply the confirmed incident overlay and compare baseline versus scenario
capacity. Feature 6: use OR-Tools for resource-conserving response alternatives,
including donor reserves, receiving constraints, budgets and transport inputs.
