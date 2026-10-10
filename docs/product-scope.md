# HealthGrid: finalized product scope

HealthGrid helps the Ministry and hospitals anticipate service-capacity gaps,
coordinate a feasible response across facilities, and choose investments that
reduce recurring bottlenecks. Its foundations are capacity prediction and
intelligent resource allocation. The dashboard connects the decisions to their
evidence, assumptions, responsible people and reported outcomes.

## Three decisions

1. What can we deliver? Current and projected usable capacity by service and place.
2. What should we do? Feasible response alternatives using available resources.
3. What should we fund? Costed investment packages that improve future capacity.

## Users

- Hospital coordinator: supplies operational reports, checks proposed actions,
  confirms facility constraints and records execution progress.
- Ministry planner: reviews network gaps, compares responses and funding packages,
  records decisions and follows outcomes.

For the demo, explicitly labeled persona views may simulate this workflow.
Persona switching is not authentication or authorization. Real deployment needs
enforced roles and permissions before operational use.

## Two modes, one shared system

### Routine planning

Update reports -> validate data -> calculate usable capacity -> forecast demand
and resource gaps -> compare responses -> compare investments -> record a decision
-> compare subsequent observations with the expected result.

Start with a seven-day forecast. Show history, forecast uncertainty, resource
bottlenecks and data freshness. Historical service activity may be constrained by
available capacity; label it as an activity proxy when true demand is unavailable.

### Crisis response

Declare incident -> confirm affected services and assumptions -> estimate the
network impact -> generate feasible response options -> review and record a plan
-> update the incident and recompute as reports arrive.

The planner can create an incident from a structured form or a short situation
report. Include affected facilities, incident start, expected duration, service
outages, unavailable resources, demand changes and access/transfer restrictions.

AI proposes structured interpretations and flags incomplete or conflicting reports.
The user confirms these before they become scenario inputs. All unverified inputs
remain visibly labeled; missing values must not silently become zero or available.

A crisis is an overlay on a saved baseline, not a rewrite of historical records.
The initial crisis view covers the next 24 hours. Sudden-event demand overrides are
scenario assumptions, not predictions learned from routine historical data.
Revisions create new run versions so earlier decisions remain traceable.

## Fast response design

- Reuse the latest validated facility snapshot; show its age.
- Allow structured incident entry without waiting for AI interpretation.
- Calculate deterministic capacity effects before generating narrative explanations.
- Run optimization with a configurable time limit. Return a feasible plan if one
  has been found, with its actual solver status and elapsed time.
- Distinguish optimal, feasible, infeasible, and unknown/no feasible plan found.
  A timeout without a plan must not be presented as proof of infeasibility.
- Show remaining gaps and required confirmations; never invent a feasible action.
- Measure time to first feasible plan on the demo dataset. No emergency response
  latency or real-world reliability guarantee has been established.
- The system proposes plans; it does not autonomously dispatch supplies, transfer
  patients, assign staff, or spend money.

## Calculation and AI responsibilities

- Capacity rules translate resources into service capacity under explicit,
  configurable service requirements. Demo rules are illustrative, not clinical standards.
- Forecasting estimates future demand/resource use and reports validation results.
- Optimization checks quantities, donor reserves, receiving capacity, eligibility,
  travel/lead time, budget and resources shared between services.
- AI interprets reports, classifies issues requiring review and explains computed
  alternatives using supplied evidence. It does not establish numerical feasibility.
- The planner chooses objectives and trade-offs; display those choices. An
  optimizer's preferred plan depends on the stated objective and assumptions.

## Response and investment comparison

Compare do-nothing, response and investment scenarios using capacity, unmet demand,
cost, time to effect and unresolved constraints. Preserve service-specific units;
do not add incompatible services into a single capacity number.

Investment candidates are entered with costs, operating costs, dependencies,
resource effects and implementation times. The engine selects among these
candidates; it must not invent project costs or health benefits. A project cannot
contribute capacity before it becomes operational. Compare options on the same
evaluation horizon and show future investments separately from immediate relief.

## First demonstrable release

Use three fictional hospitals, multiple resource types and one complete service
model. Keep facilities, resources and service requirements configurable so the
platform can be extended across services without duplicating its workflow.

Deliver the five existing screens: overview, facilities, forecasts, scenarios and
investments. Crisis mode lives within overview/scenarios and uses the same backend
engines. Include CSV/manual reports, routine forecasting, an incident form,
response comparison, a small investment catalog, and recorded decision status.

Use draft -> pending review -> approved/rejected -> in progress -> completed states.
Approval does not prove execution or impact; subsequent reports provide evidence.
No live hospital integration, automatic dispatch, national-scale validation, or
patient-level clinical triage is included in this release.

## Demonstration and acceptance

1. Show a baseline network and an emerging gap under routine conditions.
2. Introduce a sudden outage and demand surge at Demo Hospital A.
3. Show changed usable capacity and neighboring facility pressure.
4. Compare feasible immediate responses against the do-nothing baseline.
5. Show a recurring gap and compare investment packages under an entered budget.
6. Record a chosen plan and owner, then add a follow-up report and show the difference.

Every displayed result must be tied to its scenario/run, time horizon, input
snapshot and assumptions. Synthetic data must remain labeled. No action may
overdraw a sending facility, double-count shared resources or ignore an active
restriction. Insufficient data and infeasible situations need explicit UI states.

This document defines the target behavior. The repository currently contains a
scaffold; these domain features remain to be implemented.
