# Investment package frontend

Agreement: `docs/feature-7-contract.md`. Frontend changes are confined to `apps/web`.
The investments schemas/router and canonical Feature 7 catalog/examples remain
placeholders. This screen does not imply that funding optimization or server
investment persistence is implemented.

## Source and editor

A saved, validated allocation comparison with a proposed summary links to
`/investments?allocation_run_id=...`. The existing allocation GET loads the frozen
post-transfer summary, inherited simultaneous demand, coverage, source references
and transfer assumptions. Invalid/unvalidated or missing proposed summaries fail
visibly. Current hospital reports never replace the funding baseline. Source
transfers are assumed for this scenario, not recorded as executed.

Budget (USD cents), UTC planning/evaluation dates, positive full-month operating
allowance, catalog label and evaluation assumptions are explicit. Blank quantities
remain unknown. Prior transfer costs are shown separately and are not charged twice.

Candidate rows edit IDs/names/hospital, capital and recurring costs, implementation
days, integer resource additions, dependency-only projects, prerequisites, exclusive
asset groups, source notes and confirmation timestamps. Renaming/removing a referenced
project leaves visible invalid references for review rather than rewriting assumptions.
Form feedback covers integers, dates, catalog membership, duplicate effects/IDs,
unknown/self/cyclic prerequisites and units. Missing evidence remains visibly
ineligible; it is not inferred from inventory. The backend owns definitive validation,
cost/readiness calculation, source timing rules and numerical feasibility.

The backend starter catalog is not called because no schema/endpoint is implemented.
Users can edit draft candidates; **Optimize package** is explicitly disabled in
connected mode. The editor does not calculate project cost, capacity, benefit, ready
dates or optimal selection. No OpenAI integration is needed.

## Explicit browser demonstration

`/investments?mode=example` uses a frontend-owned display fixture derived from the
Feature 7 agreement and Feature 6's shared source summary. It is not a canonical
wire payload or engine output. Load the synthetic inputs/catalog, inspect them,
acknowledge review and show the fixed result:

- Budget USD 3,000; full operating allowance 3 months; evaluation 30 days after the
  explicitly assumed source transfer completion.
- Selected repair + commissioning, ready after 10 days. Repair is a prerequisite
  with no working-resource effect; commissioning supplies five working monitors.
- Supplied cost: USD 1,500 capital + USD 900 operation = USD 2,400; USD 600 remains.
- Supplied B modeled capacity 3 -> 8; included covered demand 6 -> 11 and unmet 5 -> 0.
  C remains excluded; its demand is uncounted rather than zero.

Only the exact unchanged synthetic inputs have a display result. Editing anything
invalidates it and requires the backend solver; lowering budget or moving evaluation
cannot produce a newly optimized recommendation in this preview. Local saving uses
an independent versioned browser key and `proposal_id` URL. Reloading restores the
stored input/catalog/source/result without a new solve or catalog fetch. Storage
errors remain visible and previous data is not reset.

A separate hypothetical-state panel previews incomplete inputs/candidate exclusions,
no improvement, feasible incumbents, unknown timeout without a plan and proven
infeasibility. These cannot be saved as calculated funding results. Proposed benefits
and selected projects are withheld without validation and a feasible/optimal
incumbent. Unknown is not proven infeasible; optimal may retain unmet demand.

## Integration after teammate contracts

When backend/data publishes Pydantic/OpenAPI, starter catalog and shared examples:

1. Regenerate API types and replace editor-to-wire mappings with generated schemas.
2. Connect the agreed catalog GET, investment POST and saved-run GET through the
   existing proxy. Never silently replace request failures with browser examples.
3. Submit the complete visibly reviewed catalog/constraints; do not auto-retry an
   ambiguous save. Protect edits from outdated catalog/calculation responses.
4. Map supplied ready timestamps, operating allowances, total/remaining costs,
   resource effects, exclusions, solver settings/versions/duration and comparisons
   without frontend recomputation. Demand/coverage inherits the frozen allocation.
5. Reopen by investment run ID, preserving original inputs and catalog. Changed
   constraints create a new run, not an overwrite. Funding remains for human review.

## Verification

`npm run typecheck --prefix apps/web` and `git diff --check` passed. Per the Feature 7
agreement, no frontend test suite, production build or browser check was run.
User review should cover saved-source navigation, all project fields/dependencies,
unknown versus zero, review acknowledgement, input edits hiding old outcomes,
explicit example package costs/readiness/gaps, hypothetical states and local saved
proposal reopening. Real optimization/persistence acceptance awaits teammates' API
and OR-Tools work; no backend changes were made in this task.
