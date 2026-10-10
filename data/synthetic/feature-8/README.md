# Fictional follow-up evidence

These numerical examples compare the frozen Feature 7 expectation (A=3, B=8
simultaneous modeled service places; C excluded/unknown) with new reported evidence.
They are not public HTTP contracts, execution events, patient outcomes or evidence
that a project caused an improvement. Teammate 2 owns those wire contracts and
saved decision/review records.

The frozen requirement profile is `demo-v1`: one physical bed, half a nurse and
one working monitor per simultaneous service place. Source baseline: October 10,
2026 at 09:00 UTC. Window starts at the assumed transfer completion, 11:00 UTC.
Investment expected date: November 9 at 11:00 UTC. Ordinary review capture is
November 9 at 11:05 UTC; no comparison claims the expected date was met on time.
The decision's human target completion date cannot replace this source expected date.

| Input file | Hospital B outcome |
| --- | --- |
| `insufficient.input.json` | Planned quantities have no report IDs/timestamps: unknown |
| `supported.input.json` | Fresh 18 beds, 9 nurses and 8 monitors: capacity 8, difference 0 |
| `shortfall.input.json` | Fresh 6 monitors: capacity 6, difference -2 |
| `zero.input.json` | Fresh explicit 0 monitors: capacity 0, difference -8 |
| `unavailable.input.json` | Current reported unavailable service: explicit modeled 0 |
| `stale.input.json` | Monitors are 24 hours and one second old: unknown, despite cached current label |
| `partial.input.json` | A's nurse report missing; B remains comparable, incomplete coverage |
| `early.input.json` | One hour before expected date: capacity visible, target assessment too early |
| `late.input.json` | Two days after expected date: current capacity 8; no on-time or causal claim |

`demo-expectations.json` contains manually specified row outcomes and coverage.
`requirement-profile.json` matches the existing frozen demo profile. Inputs freeze
complete snapshots, observation IDs, observed/received timestamps and review timing.
Missing expected capacity/demand stays null. Planned demand is not newly measured
demand; differences are observed minus expected and may be negative or positive.
No national total or success percentage is calculated from incomplete facilities.

The pure kernel re-evaluates freshness at capture time, checks observation window
membership and provenance, then calls the existing capacity engine. Cached freshness
flags cannot make old observations current. Only copied snapshots are normalized;
reported quantities and source expectations are never mutated. Reported completion
is outside this numerical interface and never creates evidence.

Explicit reported unavailable status is the captured current service state and
therefore gives modeled zero even with missing resource observations, which remain
visible. It is not a historical status claim. Limited service has no quantified
restriction and remains unknown even when resource reports are fresh.

The Feature 1 API integration test captures old reports, appends fresh B reports to
reach 8, then appends 6 monitors and captures a new shortfall. Earlier captured inputs
and results remain unchanged. Demo A is still limited in Feature 1; fresh resource
quantities alone cannot reopen it. These numerical fixtures explicitly supply an
operating A to illustrate full A/B evidence coverage. Saved decision-review API persistence and history are now integrated and checked
against the actual engine in `test_decisions_api.py`.

Checks use the requested Python 3.14 environment; Python 3.12 remains the project
target. The integration adds canonical DTO binding, frontend/API wiring and read-only review history.
No live database is changed by these tests.

```bash
.venv/bin/python -m pytest apps/api/tests/test_outcome_engine.py apps/api/tests/test_outcome_evidence_api.py apps/api/tests/test_capacity_engine.py -q
```
