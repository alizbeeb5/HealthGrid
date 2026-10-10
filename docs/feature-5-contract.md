# Feature 5: Emergency assessment and capacity-impact simulation

Status: design only. This agreement supersedes the earlier emergency-intake draft.
Use the existing stack. Features 1–4 remain the reported-data and forecast foundations.

## Outcome

Declare an incident from the network dashboard, assess its report quickly, confirm
the affected hospitals/services/resources, then compare modeled capacity before
and under the incident assumptions. Save the evidence and immutable run inputs.
This feature identifies the capacity effect; Feature 6 will compare responses with
OR-Tools. It does not infer patient redistribution or spare admission capacity.

Workflow: overview -> Declare incident -> manual form or situation report ->
AI assessment/extraction -> edit and confirm assumptions -> capture baseline ->
simulate -> compare hospitals -> save/reopen the run.

One complete demo: DEMO-B has 5 modeled emergency-care places. Enter a power-failure
report and confirm that its emergency service is unavailable. The scenario shows
5 -> 0, capacity change -5. DEMO-A remains unknown and DEMO-C unavailable/0.
The original hospital reports remain unchanged. No transfer plan is implied.

## Build in this order

1. Manual incident form, save/reopen draft, and confirm inputs.
2. Immutable baseline plus deterministic capacity comparison.
3. Fast AI assessment and optional extracted draft fields.
4. Independent failure states, evidence review and saved-run details.

The manual path must work without an OpenAI key. Do not wait for field extraction
to display completed fast-assessment flags. No paid model calls at app startup.

## AI and numerical responsibilities

Use the verified official APIs:
https://developers.openai.com/api/docs/guides/decisions
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses

Decisions produces fixed review answers using emergency-review-v1:
- outage_reported: yes / no / unclear
- multiple_facilities_reported: yes / no / unclear
- resource_loss_reported: yes / no / unclear
- clarification_needed: yes / no / unclear

This classifies the report, not clinical severity. Never bypass confirmation based
on a flag. Preserve per-answer refusal as null with answer_status=refused.
Use the documented Decisions model gpt-6-luna; confirm SDK support when implementing.
Responses Structured Outputs extracts an editable draft and supporting excerpts.
Configure its supported model separately. Neither API calculates capacity or resource
feasibility. The Python engine performs impact calculations; OR-Tools comes later.

Both adapters are server-side and receive the original report and allowed catalog
IDs. Report text is data, not instructions to use tools. No tools/dispatch permissions
are supplied. Return missing values as null/absent and ask questions; never invent
facility IDs, resource counts, outage duration or affected services.

Each extracted non-default value has evidence: field_path and source_excerpt, an
exact substring of the report. Validate excerpts and catalog matches before showing
the proposal. An ambiguous name requires user selection. Defaults are visibly
labeled policy assumptions. An excerpt proves source linkage, not factual accuracy.

Independent assessment_status/extraction_status: completed / unavailable / failed /
refused. Record model, elapsed_ms and rubric_version for assessment. Extraction
returns candidate (null on failure), evidence[], questions[] and warnings[].
Use a configurable 15-second timeout per provider call, no automatic retry; failure
must not erase manual edits. Display measured elapsed time without promising a
complete emergency response latency. Refusal/incomplete output is a handled state.

## Shared input contract

Backend owns Pydantic schemas and examples; frontend generates types from OpenAPI.
Reuse snake_case, string identifiers, existing service/resource enums and units,
nonnegative finite quantities and UTC-aware timestamps. Extra fields forbidden.

IncidentDraftInput:
- title: string, 1–200 characters
- report_text: string/null, max 10,000
- service_id: Identifier/null; select one service for the first comparison
- starts_at: UTC/null
- expected_ends_at: UTC/null; if both supplied, end must be after start
- affected_facility_ids: sorted unique Identifier[]; empty allowed in draft
- service_overrides: ServiceOverride[]
- resource_overrides: ResourceOverride[]
- assumptions: string[]; each max 500

IncidentInput confirms the same shape but requires service_id, starts_at, at least
one affected facility and at least one override. Every supplied value is validated
even in a draft. A bare report with missing structure can be saved as a draft.

ServiceOverride: facility_id, service_id, status (operating/limited/unavailable),
restriction_note (string/null). All service IDs equal the selected service in this
milestone. Limited requires a note and yields unknown capacity; never use a 50% rule.

ResourceOverride: facility_id, resource_id, available_quantity, unit. Quantity is
absolute scenario availability, not a loss to subtract. Require matching catalog
units, resource applicability and whole counts where fractions are disallowed.
One override per facility/service or facility/resource pair. Override facilities
must be in affected_facility_ids and offer the selected service. Resources outside
the requirement profile may be recorded, but explain that they do not affect the
current modeled estimate. Preserve unknown baseline resources unless explicitly set.

Simulation is one modeled state after the declared change, using reports captured
at confirmation. starts_at/expected_ends_at describe the incident; this milestone
does not reconstruct past conditions or model recovery over time. Show that temporal
assumption in review and results. Demand changes, routes and transport restrictions
are later extensions. No inferred demand/shortage calculation without those inputs.

## Baseline, revisions and runs

Draft -> confirmed is an input-review workflow, not operational action approval.
Create immutable revisions. IncidentRevision fields: incident_id, revision_id,
parent_revision_id, status (draft/confirmed), input, created_at, confirmed_at,
confirmed_by and baseline_id. The last three are null for drafts. confirmed_by is a
demo display name, not authenticated identity; show simulated roles as such.

Confirmation atomically stores the reviewed input and a baseline with baseline_id,
captured_at, facility_snapshots (all hospitals offering the selected service, ordered
by facility_id), requirement_profiles (full validated content, not just versions),
and schema_version=1. Capture each snapshot once using one shared timestamp via
facility services. Missing/stale reports remain visible. Never write scenario
quantities into observations/history or mutate the captured baseline.

Allow one confirmation per draft using a database uniqueness constraint. Stale,
already-confirmed or concurrent requests return 409 with the existing revision
reference where applicable. Do not automatically retry an ambiguous confirmation.
New incidents/drafts are the edit path for this milestone; no PATCH overwrites.

A pure engine `simulate_incident(baseline, incident) -> IncidentImpact` copies baseline
inputs, applies reviewed overrides and reuses the existing capacity engine. Every
scenario override is labeled as an assumption; it must not inherit the old reported
observation's ID/timestamp as proof of the new quantity. Persist baseline inputs,
overrides and computed results separately. Unknowns remain null, unavailable is 0.

IncidentImpact:
- incident_id, revision_id, baseline_id, service_id, capacity_unit
- rows: list ordered by facility_id, each with facility (existing Facility),
  baseline_capacity and scenario_capacity (existing ServiceCapacityResult),
  capacity_change (signed integer/null), affected (boolean), and applied_overrides
- capacity_change = scenario estimate minus baseline estimate only when both known;
  otherwise null. Unaffected rows use unchanged baseline results.

No combined network total or automatic patient-flow simulation in this milestone.
Show the existing per-facility evidence, baseline timestamp and profile version.
Use saved profile content. Later reports cannot change a saved run.

SimulationRun adds run_id, created_at, engine_version, schema_version and impact.
Compute against the confirmed revision's baseline, not live data. Repeat calls
return the same saved run for that revision/engine version (enforce uniqueness).
Configuration/calculation failures fail the request and save no partial run.

## API agreement

| Endpoint | Agreement |
| --- | --- |
| POST /api/v1/intelligence/incidents/assess | {report_text} -> status, answers, model, rubric_version, elapsed_ms |
| POST /api/v1/intelligence/incidents/extract | {report_text} -> status, candidate, evidence, questions, warnings, model, elapsed_ms |
| POST /api/v1/scenarios/incidents | IncidentDraftInput -> IncidentRevision, 201 |
| GET /api/v1/scenarios/incidents | {items: latest revisions}, newest created_at first, ID tie-break |
| GET /api/v1/scenarios/incidents/{incident_id}/revisions/{revision_id} | IncidentRevision |
| POST /api/v1/scenarios/incidents/{incident_id}/confirm | {draft_revision_id, input: IncidentInput, confirmed_by} -> confirmed revision, 201 |
| POST /api/v1/scenarios/incidents/{incident_id}/revisions/{revision_id}/simulate | Confirmed revision -> saved SimulationRun, 201; existing run 200 |
| GET /api/v1/scenarios/runs/{run_id} | Saved SimulationRun |

The assess endpoint's status is assessment_status; extract uses extraction_status.
Invalid report input is 422; provider unavailable is a 200 component state, not
fake successful output. Use a scenarios-owned error enum with the existing envelope
shape: invalid_request (422 fields), incident_not_found/revision_not_found/run_not_found
(404), revision_conflict (409), incident_not_confirmed (409). Existing Feature 1 error
schemas stay unchanged. Technical errors are 500, never unknown/zero incident impacts.
Add scenarios-owned ORM models/migrations for revisions, baselines and runs.

## Three teammate tasks

### Teammate 1 — Emergency UI and comparison

Own apps/web scenario components/page/API clients and overview Declare incident link.
Build manual form, draft saving/reopening and confirmation first. Integrate separate
AI assessment and extraction states with evidence and questions. Protect user edits:
discard AI results after report changes; never overwrite edited fields silently.
Build baseline-versus-scenario hospital table, delta, bottleneck/status explanation
and saved-run reopening. Show unresolved data and explicit scenario assumptions.

Done: overview -> declare B outage -> review -> confirm -> simulate -> see 5 -> 0
and -5 -> reload saved run. The same journey works without an AI key.

### Teammate 2 — Persistence and deterministic impact

Own modules/scenarios schemas/router/service/repository/models/migrations,
engines/scenarios.py, shared examples and OpenAPI. Publish contracts first, implement
draft/confirmation with transaction and duplicate protection, capture profiles and
snapshot evidence, then implement the pure overlay and saved simulation endpoint.
Reuse capacity calculations through their agreed interfaces. Coordinate any public
catalog service additions, settings/dependency changes and schema changes.

Done: manual flow persists, 5 -> 0 is reproducible, baseline/reports remain unchanged,
unknown/stale data is preserved, resource overrides validate units/counts, and
duplicate/conflicting requests or failed transactions behave as specified.

### Teammate 3 — Fast AI interpretation and report cases

Own modules/intelligence adapters/service/router and schemas agreed with backend;
synthetic report fixtures and focused provider tests. Implement the four Decisions
questions and separate Responses extraction. Validate evidence/catalog matches.
Handle timeout, refusal, incomplete output, missing key and ambiguous/conflicting
reports. Prepare six expected cases: clear outage, missing dates, ambiguous hospital,
conflicting quantities, explicit resource loss and embedded tool instructions.

Done: fixed flags and extracted proposals match the contract; no invented data;
manual entry survives all provider failure cases. Record latency/model/rubric metadata.
Ordinary tests stub providers. Paid live checks run only when deliberately invoked.

## General agreement and merge order

1. Freeze Pydantic schemas and example JSON first; backend owns wire changes.
2. Branches: feature-5/frontend, feature-5/scenarios, feature-5/intelligence.
   Each owner changes their files; coordinate shared routers/dependencies/migrations.
3. Frontend can use labeled examples while manual persistence/simulation and AI work
   proceed independently. Never fall back to examples silently on API failure.
4. Merge manual incident/baseline, simulation, then AI integration. Regenerate OpenAPI
   and frontend types for schema changes. Reuse Feature 1–4 IDs and units.
5. Focused engine/API/provider tests; the user handles browser checks. No automatic
   frontend builds/tests or live AI calls by the reviewing agent.
6. Joint finish includes confirming B outage, saved simulation, a later real resource
   update, and proof that reopening the saved run retains its original baseline.

Feature 6 takes these confirmed inputs into Google OR-Tools to compare feasible
responses, including donor reserves, receiving capacity and resource conservation.
