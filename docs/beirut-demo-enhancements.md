# Beirut explosion demonstration and product polish

Active milestone: strengthen the existing eight-feature workflow. Do not add a
ninth domain feature before the demonstration is coherent and usable.

## Product claim to demonstrate

HealthGrid helps a Ministry see where care will become constrained, compare
responses across hospitals, and fund the remaining bottlenecks while retaining
the evidence behind each decision. The visible unit of work is a service gap and
a response decision, not an inventory row.

Show the reasoning chain: incident -> service interruption -> assumed surge ->
limiting resources -> feasible redistribution -> remaining gap -> funded recovery
-> reported implementation -> fresh outcome evidence. A recommendation should
always show why it helps, what prevents alternatives and what it leaves unresolved.

## Historical basis and scenario boundaries

The setting is the Beirut port explosion of 4 August 2020. WHO's 5 August report
described three nonfunctional hospitals, two partly damaged hospitals, overloaded
receivers and transfers beyond Beirut. It also described trauma/surgical supplies.
Use this to motivate a disrupted network and supplies context, not to infer any
individual facility inventory or route:
https://www.who.int/news/item/05-08-2020-plane-carrying-who-trauma-and-surgical-supplies-arrives-in-beirut-lebanon

The AUB BASS study describes an early influx of mildly injured patients followed
by increased arrivals of more severely injured patients and substantial surgical
activity. This supports distinct response phases rather than one undifferentiated
surge. It does not supply our assumed arrivals or resource-consumption rates:
https://scholarworks.aub.edu.lb/items/748f2c80-8762-4ad5-8698-68044117dd0a

Use the persistent label “Beirut explosion exercise — synthetic operational data.”
The facility identities, coordinates, resource quantities, demand, ratios, costs,
routes and timestamps within the event day are invented demonstration inputs.
Use fictional hospitals in recognizable geographic areas. Do not attach fabricated
shortages or decisions to actual hospitals. Show historical context in a small
source drawer, separate from simulated reports and inferred recommendations.

## Resource and service expansion

The code already models beds, nurses and monitors; oxygen stock is recorded but
does not establish modeled service capacity. The first new pack supplies 19
resource types and a five-resource emergency stabilization profile.

| Domain | Resources | First integration behavior |
| --- | --- | --- |
| Emergency stabilization | Treatment spaces, assigned nurses, emergency physicians, working monitors, supplied oxygen points | All five constrain simultaneous modeled capacity |
| Surgery | Operating theatres, surgeons, anesthesia clinicians, sterile instrument sets | Operational context first; a separate configured service profile is required for numerical estimates |
| Respiratory support | Working ventilators, oxygen stock | Display availability; no conversion of liters into patient places |
| Trauma supplies | Dressing kits, red-cell products separated by blood group | Inventory/evidence display; no automatic patient matching or generic blood pooling |
| Diagnostics | CT scanners and X-ray units | Surface outages and reported availability; no invented throughput |
| Transport | Available ambulances and reviewed route status | Show response constraints; vehicles/dispatch scheduling require explicit modeling |
| Infrastructure | Working generators and diesel stock | Surface power vulnerability; no stockout time without confirmed consumption assumptions |

The initial numerical path remains a single service. Resource counts do not become
new service capacities automatically. Before making blood, oxygen, fuel or kits
affect forecasts, specify horizon, consumption, replenishment, units and uncertainty.
Do not sum independent service estimates that share staff, equipment or supplies.
Add surgery/critical-care profiles after explicit resource reservations are agreed.

## One canonical scenario pack

Use `data/synthetic/beirut-explosion/` as the presenter scenario source. The launcher loads
resource/profile/snapshot fixtures and generates saved plans through the existing
capacity, allocation and investment services. Existing feature fixtures remain regression examples;
they must not appear as separate competing stories during presentation.

Facility roles:

1. Port-area hospital: interruption despite physical resources still being listed.
2. West Beirut receiver: monitor shortage despite sufficient beds and staff.
3. East Beirut receiver: staff shortage despite available equipment.
4. Mount Lebanon reserve: can supply monitors while retaining protected capacity.
5. Unconfirmed facility: insufficient reporting, visibly excluded from estimates.

Expected core narrative over the three included operating facilities:

- Assumed demand totals 48 simultaneous service places, not 48 arrivals or casualties.
- Post-incident coverage is 28. Closed and unconfirmed facilities remain explicitly
  outside this subtotal; this is not the historical Beirut network total.
- Move 8 approved monitors from Mount Lebanon to the West receiver: coverage 36,
  remaining gap 12. Sending more monitors to the East receiver does not resolve
  its nurse bottleneck.
- A separately dated recovery package restores 4 monitors at the West receiver
  and funds 4 additional confirmed nurses at the East receiver for the evaluation
  shift: coverage 48 against the same assumed demand, at $10,000 modeled cost.
  Staffing availability and roster coverage are assumptions, not an optimizer
  creating personnel. Recovery estimates cannot be described as immediate relief.
- Completing action records alone changes no inventory. Fresh reports can support
  the expected result or reveal an unresolved gap.

## Make the Ministry workflow easier

Keep existing URLs but organize the interface around five user jobs:
Situation overview -> assess emergency -> compare response -> fund recovery ->
track decisions. Hospitals and forecasts remain supporting views.

Overview above the fold should answer:

- Which services/hospitals need attention, and what is the limiting resource?
- How much planned demand is covered now, and how much could the proposed response cover?
- Which decision needs review next, who owns it, and what is its deadline?
- Which reports are missing or too old to rely on?

Use a situation banner, map, short prioritized issue list and one primary next
action. Each issue card states impact, cause, recommended next step and freshness.
Do not fabricate values when no incident/plan is selected: explain the missing step.
Retain a visible service selector and explicit subtotal coverage.

Replace technical-first labels with plain language. Display hospital/resource names
instead of IDs. Put solver versions, raw profiles and detailed evidence in expandable
sections; show meaningful limitations near the affected decision. Persist incident
and proposal context across links so users do not re-enter IDs. Load reviewed demo
constraints into forms and highlight the few choices that need human confirmation.

Plan comparison should lead with coverage improvement, remaining gap, affected
hospitals, cost and time. Show a short “Why this action?” explanation from computed
constraints. Include at least one rejected alternative: adding equipment where
staff is limiting. Do not claim formal causal attribution or lives saved.

## Presentation flow, about five minutes

1. Establish the historical setting and identify synthetic values on the map.
2. Activate the incident report and review the extracted assumptions. The explosion
   itself is not predicted. Routine forecasts provide context; surge inputs are
   explicit scenario assumptions.
3. Show physical spaces versus usable modeled capacity and two different bottlenecks.
4. Compare no action with the checked transfer proposal and explain donor protection.
5. Show why the remaining gap needs a different recovery investment, at a later date.
6. Record the decision and compare fresh follow-up evidence with its expected result.

Keep a reproducible offline report/extraction example and disclose it as prerecorded.
Live AI review remains an explicit optional action; do not fabricate a live response
or latency. Measure actual solve times on the demo, not a promised emergency SLA.

## Implemented in this milestone

- Isolated SQLite launcher with fresh/resume behavior and migration 0008.
- Five fictional facilities, 19 resources, a five-resource capacity profile and
  63 days of synthetic history ending 3 August. Forecasts do not predict the blast.
- One confirmed incident and frozen baseline, real saved monitor allocation and
  recovery funding runs, linked decision drafts and their prerequisite.
- Persisted assessment/response/recovery clock, transactional rehearsal controls,
  append-only follow-up reports and two frozen outcome reviews.
- Ministry navigation, synthetic context banner, saved scenario comparison,
  cause/action cards, grouped resource reports and human-readable names.
- Results before planning forms; detailed constraints and solver evidence remain
  expandable. Forms can load the exact saved exercise assumptions.
- Prerecorded report interpretation explicitly labeled as synthetic. Optional
  live AI actions retain their explicit live labels and server-side keys.
- Automatic API mode during the exercise so old browser fixtures do not mix in.

The user assigned this implementation to a single driver. No new teammate tasks
are required. Secondary service profiles, consumable depletion, non-monitor
allocation and authenticated production operations remain outside this milestone.

## Verification and remaining rehearsal

240 backend tests and 22 subtests passed, covering capacity, forecasting, allocation, investments, outcome
comparison, migrations and the complete staged exercise. Exercise checks cover
rollback, repeated-stage idempotency, frozen proposals, initial forecast history,
and rejected equipment-only alternatives. Python lint and generated contracts
are checked. Python 3.12 and Node 22 are used.

The sandbox's synchronous HTTP TestClient stalled, so exercise integration uses
real domain services and transactional route handlers directly. HTTP transport
and the running browser flow are not claimed verified. Per user instruction,
frontend builds, tests and browser checks were not run; no paid AI request was made.
Use `demo-scenario.md` for the user's browser rehearsal.


## Focused Beirut presentation update

The main journey now uses dedicated incident, recovery funding and outcome views.
Repeated API/demo warning banners and irrelevant single-option selectors are
removed from this path. One neutral synthetic-data strip remains; evidence gaps,
blocked operations and forecast shortages still show meaningful warnings.

AI advice is available directly on the saved incident screen. It generates a
prioritized action brief on explicit user request. Funding shows selected projects,
setup/operating costs and a dollar-budget comparison form. Outcomes show the two
canonical decisions and expected-versus-reported capacity, with controls to compare
before/after evidence. Generic development editors remain outside the normal path.

History now grows through the preceding complete exercise day on phase advancement
or launcher resume. Existing history is never overwritten. A recovery forecast
uses synthetic post-transfer daily reports, not future funded capacity. Regression
checks cover older short-history repair, resume idempotency, three receiving-hospital
forecasts at recovery, and absence of future staffing benefits in history.


## Workspace navigation and concise layout

Desktop uses a persistent sidebar; mobile uses compact navigation. The dashboard
has Map, Hospitals and Plan comparison views instead of stacking every section.
Incident impact sits beside AI guidance. Funding and Outcomes keep their controls
beside the principal result. Forecasts switch between Chart and Daily values.
Hospital report forms remain beside resources while scrolling on desktop.

Repeated introductory text is shortened; missing evidence and relevant uncertainty
remain visible, with detailed provenance expandable. This is a presentation-only
change. Code was reviewed and whitespace checks passed. Per user preference, no
frontend build, automated frontend test or browser check was run.
