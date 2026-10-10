# Fictional monitor allocation dataset

All hospitals, resource-loss assumptions, demand and route approvals are synthetic.
These files do not modify reported observations or authorize transfers.

The effective scenario has A: 12 beds, 6 nurses, 4 monitors; B: 18 beds, 9 nurses,
2 monitors. C is unavailable and excluded. The demo profile requires one bed,
one monitor and half a nurse per simultaneous service place.

A requires three places and approves moving one monitor while retaining three.
B requires eight places and accepts one monitor. The approved direct route takes
30 minutes and costs USD 100, within the 60-minute/USD 100 limits.

Expected result: one monitor A → B; A capacity 4 → 3, B capacity 2 → 3;
covered demand 5 → 6, remaining unmet demand 6 → 5. Excluded demand stays unknown.

Files contain frozen effective snapshots, explicit incident assumptions, a demo
requirement profile, planning inputs and four reproducible mathematical-kernel
cases. The tiny-time-limit case illustrates unknown/no incumbent, not proven
infeasibility. Conflicting reserves are tested separately as infeasible.

Public engine types are backend-owned in `app.modules.allocation.schemas`.
`optimize_allocation` accepts those types; temporary-shaped kernel fixture records
remain internal to tests. Canonical HTTP request/response examples live in
`contracts/examples/feature-6` and are checked against the actual engine/API.
The frontend uses those generated wire types rather than kernel fixture shapes.

The pure CP-SAT engine minimizes unmet simultaneous places, then cost, then items.
Sequential solves share one total time budget; only proven optima are frozen.
Every incumbent is independently checked and its capacities recomputed through
the existing capacity engine. Inventory, donor floors, receiving limits, approved
routes, budgets and deadlines are enforced. Receiving hospitals cannot re-export.
No database, HTTP or AI call is made by the engine.

Checks run with the existing Python 3.14 environment and OR-Tools 9.15.6755; the
shared project deployment target remains Python 3.12. The backend regression suite
also verifies immutable results and unchanged reports after planning.
