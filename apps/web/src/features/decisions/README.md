# Decision tracking frontend

Feature 8 follows `docs/feature-8-contract.md`. The decision schemas, shared API
examples, persistence endpoints and Python outcome engine are not implemented in
this checkout. This module does not invent a wire contract or calculate capacity.

## Review the workflow

Open `/decisions?mode=example`. This explicitly enables synthetic browser-local
records, stored under `healthgrid:decision-ui-preview:v1`. Records and fixed evidence
samples can be reopened from the board and their decision/review URLs in the same
browser. They are not server records and are not shared with other users.

1. Choose the transfer example. Enter a demo actor, owner, title, UTC deadline and
   rationale. Save the draft, submit, and record approval with an explanation.
2. Report the transfer action complete with a nonfuture UTC timestamp and evidence
   note, then mark the decision reported completed with an explanation. Blank
   actual cost means unknown, rather than zero.
3. Create the investment example and select that exact allocation decision as its
   prerequisite. Approve it, report repair completed, then commissioning completed.
   Dependencies and the allocation prerequisite block premature execution.
4. Save an explicitly selected evidence sample and reopen it. Missing evidence,
   matching capacity, below-expected capacity and early review are separate samples.
   Completing actions does not automatically create supported evidence.

Approval, execution reports and evidence support remain separate. Blockers are
visible on the filtered board. Corrections append a reason and revised report while
retaining the original. Terminal records remain available; reconsideration creates
a linked new record. Preview guards reject duplicate active/completed source
decisions and outdated local versions, but browser storage is not a transactional
or authenticated service and does not provide server idempotency guarantees.

## Integration boundary

`/decisions` defaults to the saved-proposal view. Existing generated API types are
used to inspect validated allocation and investment runs read-only via
`source_type` and `source_run_id`. Saved proposal panels link here. Decision writes
and live evidence capture remain disabled until agreed backend contracts arrive;
request errors never trigger an automatic example fallback.

The existing allocation response does not supply the complete expected-date and
baseline capture context required by decisions. Those fields remain unknown in
the read-only adapter. Investment evaluation time comes from its saved input and
is separate from the human deadline. Source transfers are not duplicated as
investment actions.

`demo-display.json` contains frontend-only synthetic display fixtures, not shared
backend payloads. Their observation windows, capture clocks, capacity differences
and classifications are fixed examples, never computed from live reports. A fixture
capture timestamp is not the time a user saved its local preview. Reviews retain
the decision version, sample evidence, observation IDs, units, profile, exclusions
and comparison coverage. They do not establish causation or clinical benefit.

When teammates implement the domain, regenerate OpenAPI/frontend types and replace
the preview adapter with the agreed endpoints for decisions, append-only events
and immutable outcome reviews. State transitions, exact-source prerequisites,
authorization, transactions, expected-version conflicts and request idempotency
must be enforced server-side. Python owns expected/observed capacity, freshness,
review windows and comparison classifications. No action report here writes
hospital observations, dispatches equipment, purchases projects or sends messages.

Per the Feature 8 agreement, user review supplies browser validation. Frontend
tests, builds and automated browser checks require an explicit request; TypeScript
and whitespace checks can run independently.
