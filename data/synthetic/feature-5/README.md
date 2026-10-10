# Feature 5: AI/data teammate handoff

All six reports in `report-cases.json` are fictional and contain no patient data.
They cover a clear outage, missing dates, an ambiguous hospital, conflicting
quantities, explicit resource loss, and embedded tool instructions. Each contains
expected Decisions flags, an editable proposal with exact source excerpts, missing
information to question, and facts that must not be invented. They are evaluation
expectations, not claims about live model accuracy.

## Implemented components

- `intelligence.adapter`: native async SDK Decisions and Responses Structured
  Outputs calls. The installed SDK is 3.28.0 and supports both APIs. No tools are
  provided; Responses storage is disabled. SDK retries are disabled.
- `intelligence.service`: independent assessment/extraction calls, bounded provider
  timeout, latency metadata, per-answer refusal, incomplete output and safe failure
  states. These services never save, confirm, simulate or edit a manual incident.
- `intelligence.validation`: exact nonblank source excerpts for every extracted
  scalar, valid evidence paths, preservation of original report text, known and
  applicable catalog IDs, service consistency, units and absolute quantities.
- `intelligence.schemas`: AI component contracts. Generic extraction types reuse
  teammate 2's actual draft model instead of defining another incident model.
- `intelligence.router`: assessment endpoint and explicit binding of extraction
  to the backend's shared draft schema. Body errors use `invalid_request`/422.
- `intelligence.catalog`: context supplied only through public facilities services;
  no cross-module repository access or persistence changes.

Source excerpts prove source linkage, not factual truth. Model proposals still
require planner review. The validator conservatively requires explicit ISO 8601
calendar/timezone evidence for proposed timestamps, an explicit service-status
word, and numeric resource quantities/explicit units. Reports using other phrasing
may need manual entry. Missing date/timezone is never filled with today's date.
A reported lost quantity is not converted to remaining availability. Ambiguous
names, conflicting amounts and insufficient details must remain unresolved with
questions. Validators add questions for missing affected facilities, selected
service, start time or overrides even if the model forgot to ask.

## Backend integration: canonical incident schema connected

Teammate 2 owns `modules/scenarios/schemas.py`. The published backend schema is
now connected directly in `intelligence.router`; its module binds extraction once
before application inclusion using the canonical model:

```python
from app.modules.intelligence.router import bind_extraction_route
from app.modules.scenarios.schemas import IncidentDraftInput

bind_extraction_route(IncidentDraftInput)
```

This binding already runs at the end of the intelligence router module. Do not
add a second call in shared router registration. It runs before application
inclusion and OpenAPI export. The router then advertises the exact typed
`ExtractionResponse[IncidentDraftInput]` rather than a generic JSON candidate.
Do not bind at request time. Both assessment and extraction routes are now registered. OpenAPI and generated
frontend schema types were refreshed after binding; teammate 1 can integrate both
component responses using these generated types.

The declared draft schema must match the agreed fields and forbid extras. The SDK
Structured Outputs helper generates the provider schema from that model; validate
it with actual canonical-model fixtures after publishing. Provider tests now use the actual canonical `IncidentDraftInput`, including the
six report fixtures. An integration test sends the extracted candidate through
the real draft, confirmation, simulation and saved-run endpoints.

AI assessment/extraction response fields follow `docs/feature-5-contract.md`.
`answers` is an ordered list of `{name, value, answer_status}` in rubric order:
outage_reported, multiple_facilities_reported, resource_loss_reported,
clarification_needed. A refused answer has value null. A partially refused
assessment retains completed answers; assessment_status is refused only when all
four answers were refused. Missing/unknown/duplicate answer names fail the whole
assessment rather than being guessed. Assessment has model, elapsed_ms and
rubric_version `emergency-review-v1`. No probabilities or clinical urgency score
are returned.

Extraction returns extraction_status, candidate, evidence, questions, warnings,
model and elapsed_ms. Candidate and evidence are cleared on failure/refusal;
questions/warnings never overwrite manual form fields. Components are separate
endpoints, so one result does not wait for or require the other. Review/confirmation
remains mandatory independently of assessment flags.

## Server-side configuration

The module's settings read the root `.env`; keep it out of Git. No key is required
for manual entry or missing-key component responses.

- `OPENAI_API_KEY`: server secret; empty means unavailable with no provider call.
- `OPENAI_ASSESSMENT_MODEL`: `gpt-6-luna`, the documented Decisions model.
- `OPENAI_EXTRACTION_MODEL`: explicitly select a supported Responses model. No
  implicit model is chosen; omitted means extraction unavailable. `gpt-6-luna`
  supports Responses and can be configured independently.
- `OPENAI_INTELLIGENCE_TIMEOUT_SECONDS`: default 15 seconds, configurable up to
  15 seconds. Both SDK network timeout and outer async call deadline are applied.

This module-local configuration avoids modifying backend-owned shared settings
or dependencies. The existing SDK version is sufficient, so no requirements/lock
change is needed. No provider request runs during imports, startup or ordinary tests.
No report/provider exception text or credentials are logged or returned on errors.
Catalog/database failures remain technical errors rather than guessed AI proposals.

## Tests and remaining integration

```bash
.venv/bin/python -m pytest apps/api/tests/test_intelligence.py -q
.venv/bin/python -m ruff check apps/api/app/modules/intelligence apps/api/tests/test_intelligence.py
```

The provider suite uses stubs and synthetic data only. It verifies six report
expectations, exact SDK request shapes, evidence rejection, invented dates/status,
valid absolute counts, loss-vs-availability, separate unavailable states, refusal,
incomplete output, timeout, no retries, latency metadata and route input errors.
Route tests use a local test app and override settings/database dependencies; no
working database or live API key is used. Run outside the sandbox if its event-loop
restrictions stall TestClient. Checks use the user-selected Python 3.14 environment.

The canonical schema is bound and the full typed API is exported. The combined
AI/scenario suite passes 89 tests, including B capacity 5 -> 0, change -5, unchanged
reported service and reopened saved result. Frontend review UI integration remains
with teammate 1. Paid live evaluation needs an explicitly invoked run and real
server credentials; it has not been performed.
Adapter tests establish handling and validation, not live extraction accuracy or
latency. Baseline capture and simulation remain teammate 2's responsibility.

Official references checked during implementation:

- [Decisions guide](https://developers.openai.com/api/docs/guides/decisions)
- [Structured Outputs with Responses](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [GPT-6 Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna)
