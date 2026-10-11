"use client";
import { useI18n } from "@/lib/i18n/context";

import { NextStep } from "../exercise/journey";
import { useExercise } from "../exercise/context";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { buttonClass, panelClass, secondaryClass, Timestamp } from "../facilities/shared";
import { blankForm, validatePlanning, type PlanningForm, type PlanningSource, type Proposal } from "./model";
import { planningFormFromRequest, calculateAllocation, reopenAllocation, exampleForm, exampleSource, loadPlanningSource, previewStore, showExample } from "./source";
import { PlanningInputs } from "./planning-form";
import { ProposalPanel } from "./proposal-panel";

export function AllocationDashboard() {
  const { t } = useI18n();
  const exercise = useExercise();
  const params = useSearchParams();
  const mode = !exercise?.enabled && params.get("mode") === "example" ? "example" : "api";
  const runId = params.get("simulation_run_id");
  const proposalId = params.get("proposal_id") ?? (!runId && exercise?.enabled ? new URLSearchParams(exercise.links?.allocation?.split("?")[1]).get("proposal_id") : null);
  const [source, setSource] = useState<PlanningSource>();
  const [form, setForm] = useState<PlanningForm>();
  const [proposal, setProposal] = useState<Proposal>();
  const [saved, setSaved] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  const generation = useRef(0);
  const lock = useRef(false);

  useEffect(() => {
    const current = ++generation.current;
    setLoading(true); setSource(undefined); setForm(undefined); setProposal(undefined); setSaved([]); setError(undefined); setNotice(undefined); setReviewed(false);
    void (async () => {
      try {
        if (mode === "example") {
          const store = previewStore(window.localStorage); const list = store.list();
          const savedProposal = proposalId ? store.get(proposalId) : undefined;
          const next = savedProposal?.source ?? exampleSource();
          if (current !== generation.current) return;
          setSource(next); setForm(savedProposal?.input ?? blankForm(next)); setProposal(savedProposal); setSaved(list);
        } else {
          if (proposalId) {
            const reopened = await reopenAllocation(proposalId);
            if (current !== generation.current) return;
            setSource(reopened.source); setForm(reopened.input); setProposal(reopened); setReviewed(true);
            return;
          }
          if (!runId) return;
          const next = await loadPlanningSource(runId);
          if (current !== generation.current) return;
          setSource(next); setForm(exercise?.allocation_input?.simulation_run_id === runId ? planningFormFromRequest(exercise.allocation_input) : blankForm(next));
        }
      } catch (cause) { if (current === generation.current) setError(cause instanceof Error ? cause.message : "Planning source could not be loaded."); }
      finally { if (current === generation.current) setLoading(false); }
    })();
    return () => { ++generation.current; };
  }, [mode, runId, proposalId, attempt, exercise]);

  function change(next: PlanningForm) { setForm(next); setProposal(undefined); setReviewed(false); setNotice(undefined); setError(undefined); }
  async function calculate() {
    if (!form || !source || lock.current) return;
    setError(undefined); setNotice(undefined);
    const errors = validatePlanning(form, source);
    if (errors.length) { setError(errors.join("\n")); return; }
    if (!reviewed) { setError("Review and acknowledge the visible inputs and their provenance first."); return; }
    lock.current = true; setPending(true);
    try {
      const result = mode === "example" ? showExample(form) : await calculateAllocation(form, source);
      setProposal(result);
      if (mode === "example") setNotice("Loaded the fixed synthetic display result. No solver executed; save it locally to review reopening.");
      else {
        window.history.replaceState(null, "", `/allocation?${new URLSearchParams({ proposal_id: result.id })}`);
        setNotice("Calculated with OR-Tools and saved for review. Reopen this link to inspect the same frozen result.");
      }
    }
    catch (cause) { setProposal(undefined); setError(cause instanceof Error ? cause.message : "No display result available."); }
    finally { lock.current = false; setPending(false); }
  }
  function save() {
    if (!proposal || mode !== "example" || lock.current) return;
    lock.current = true; setPending(true); setError(undefined);
    try {
      const store = previewStore(window.localStorage); const result = store.save(proposal); setProposal(result); setSaved(store.list());
      window.history.replaceState(null, "", `/allocation?${new URLSearchParams({ mode: "example", proposal_id: result.id })}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save the browser example. Existing saved proposals were not replaced."); }
    finally { lock.current = false; setPending(false); }
  }
  function inspectState(state: Proposal["solver_status"] | "no_improvement") {
    const base = showExample(exampleForm());
    const next: Proposal = { ...base, id: `display-${state}`, saved_at: null, transfers: [], total_cost_minor_units: null, proposed: null, validation_passed: false, remaining_gap_reasons: ["Hypothetical solver-state display example, not a solve for the entered constraints."], solver_status: state === "no_improvement" ? "optimal" : state, plan_outcome: state === "not_run" ? "needs_inputs" : state === "no_improvement" ? "no_improvement" : "no_solution" };
    if (state === "feasible") { next.proposed = base.proposed; next.transfers = base.transfers; next.total_cost_minor_units = base.total_cost_minor_units; next.validation_passed = true; next.plan_outcome = "improved"; }
    if (state === "no_improvement") { next.proposed = base.baseline; next.total_cost_minor_units = 0; next.validation_passed = true; }
    setProposal(next); setNotice("Inspecting a hypothetical result state. Reload the agreed sample constraints and display result before saving a sample proposal.");
  }
  const canSave = proposal?.id === "frontend-improved-display" && mode === "example";
  return <div className="space-y-4"><header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-wider text-teal-700">{t("Ministry / Resource planning")}</p><h1 className="mt-2 text-3xl font-bold">{t("Response plan")}</h1><p className="mt-3 text-sm text-slate-600">{t("Compare monitor transfers and the remaining service gap.")}</p></div><Link className={secondaryClass} href="/scenarios">{t("Incident & AI")}</Link></header>
    {mode === "example" && !exercise?.enabled && <div role="note" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><strong>{t("Synthetic frontend example · browser storage only")}</strong><p className="mt-2">{t("Fixed preview of the agreed resource-loss demo. No OR-Tools solve or transfer dispatch runs here; this example is separate from saved API incidents.")}</p>{!exercise?.enabled && <Link className="mt-3 inline-block font-semibold underline" href="/allocation">{t("Open saved-incident planning")}</Link>}</div>}
    {loading && <section role="status" aria-busy="true" className={`${panelClass} p-6`}>{t("Loading frozen planning source…")}</section>}
    {error && <div role="alert" className="whitespace-pre-line rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{t(error)}{!source && <button className={`${secondaryClass} mt-3 block`} onClick={() => setAttempt((value) => value + 1)}>{t("Retry loading")}</button>}</div>}
    {notice && <p role="status" className="rounded-lg bg-teal-50 p-4 text-sm text-teal-950">{t(notice)}</p>}
    {!loading && !source && !error && <section className={`${panelClass} p-6`}><h2 className="font-semibold">{t("Choose a saved incident simulation")}</h2><p className="mt-2 text-sm text-slate-600">{t("Open an incident’s saved comparison and choose “Plan resource transfers.” A service closure cannot be reversed merely by moving monitors.")}</p><Link className={`${buttonClass} mt-4`} href="/scenarios">{t("Open saved incidents")}</Link></section>}
    {!loading && source && form && <>
      <details className={`${panelClass} p-5`}><summary className="cursor-pointer text-sm font-semibold text-teal-800">{t("Inspect the saved incident and planning assumptions")}</summary><p className="mt-2 break-all text-xs text-slate-600">{t("Simulation: ")}{t(source.simulation_run_id)}{t(" · Service: ")}{t(source.service_id)}{t(" · Baseline: ")}{t(source.baseline_id)} · <Timestamp value={source.baseline_at} /></p><p className="mt-3 text-xs">{t("Planning start (UTC): ")}{t(source.planning_start_at ?? "Not supplied")}{t(". Demand, movable inventory and route approvals are separate planning assumptions. Reopening a saved proposal must retain the original input and evidence.")}</p>{!source.example && <Link className="mt-3 inline-block text-sm font-semibold text-teal-800 hover:underline" href={`/scenarios?${new URLSearchParams({ run_id: source.simulation_run_id })}`}>{t("Inspect saved incident comparison →")}</Link>}</details>
      {mode === "example" && <button className={secondaryClass} disabled={pending} onClick={() => change(exampleForm())}>{t("Load agreed synthetic constraints (A → B)")}</button>}
      {proposal && <ProposalPanel proposal={proposal} />}
      <details open={!proposal} className="space-y-4 rounded-xl border border-slate-200 bg-white p-5"><summary className="cursor-pointer text-sm font-semibold text-teal-800">{t("Adjust constraints")}</summary>
      <PlanningInputs source={source} value={form} change={change} disabled={pending} />
      <section className={`${panelClass} space-y-4 p-5`}><h2 className="text-lg font-semibold">{t("Review planning assumptions")}</h2><p className="text-xs text-slate-600">{t("Included hospitals only contribute to coverage totals. No incoming equipment may be re-exported; unavailable/limited services cannot be assumed operating. Source notes record human assumptions, not authenticated approval.")}</p><details><summary className="cursor-pointer text-sm font-semibold text-teal-800">{t("Inspect complete visible inputs")}</summary><pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-3 text-xs">{JSON.stringify(form, null, 2)}</pre></details><label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={reviewed} disabled={pending} onChange={(event) => setReviewed(event.target.checked)} />{t("I reviewed demand, donor protection, movable inventory, receiving limits, route provenance, deadline and budget. This proposal requires human review and authorizes no operational action.")}</label><div className="flex flex-wrap gap-3"><button className={buttonClass} disabled={pending || !reviewed} onClick={() => void calculate()}>{t(pending ? "Loading…" : mode === "example" ? "Show fixed proposal example" : "Calculate and save proposal")}</button>{canSave && <button className={secondaryClass} disabled={pending} onClick={save}>{t("Save browser example for review")}</button>}</div></section>
      </details>
      {mode === "example" && <details className={`${panelClass} p-5`}><summary className="cursor-pointer text-sm font-semibold text-teal-800">{t("Inspect hypothetical solver-result states")}</summary><p className="mt-3 text-xs text-slate-500">{t("Presentation examples only; these are not outcomes calculated for your inputs.")}</p><div className="mt-3 flex flex-wrap gap-2">{([['not_run', 'Needs inputs'], ['no_improvement', 'No improvement'], ['feasible', 'Feasible timeout incumbent'], ['unknown', 'Unknown / no incumbent'], ['infeasible', 'Proven infeasible']] as const).map(([status, label]) => <button key={status} className={secondaryClass} disabled={pending} onClick={() => inspectState(status)}>{t(label)}</button>)}</div></details>}

      {mode === "example" && <section className={`${panelClass} p-5`}><h2 className="text-lg font-semibold">{t("Saved browser proposal examples")}</h2>{!saved.length && <p className="mt-3 text-sm text-slate-500">{t("No example saved yet.")}</p>}<ul className="mt-3 divide-y divide-slate-100">{saved.map((item) => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><p className="text-sm">{t("Monitor transfer example · ")}<Timestamp value={item.saved_at} /></p><Link className={secondaryClass} href={`/allocation?${new URLSearchParams({ mode: "example", proposal_id: item.id })}`}>{t("Reopen saved example")}</Link></li>)}</ul></section>}
    </>}
    {exercise?.enabled && <NextStep to="investments">{t("Fund the remaining capacity gap")}</NextStep>}
  </div>;
}
