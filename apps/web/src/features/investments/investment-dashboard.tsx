"use client";
import { useExercise } from "../exercise/context";
import Link from "next/link";
import { FacilityClientError } from "../../lib/api/facilities";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { buttonClass, panelClass, secondaryClass, Timestamp } from "../facilities/shared";
import { blankForm, validateInvestment, type InvestmentForm, type InvestmentSource, type PackagePreview } from "./model";
import { exampleForm, exampleSource, exampleStore, loadSource, showExample, loadCatalogForm, createInvestment, loadInvestment } from "./source";
import { InvestmentInputs } from "./investment-form";
import { PackageComparison, SourceSummary } from "./package-comparison";

export function InvestmentDashboard() {
  const exercise = useExercise();
  const params = useSearchParams();
  const mode = !exercise?.enabled && params.get("mode") === "example" ? "example" : "api";
  const allocationId = params.get("allocation_run_id"); const proposalId = params.get("proposal_id") ?? (!allocationId && exercise?.enabled ? new URLSearchParams(exercise.links?.investments?.split("?")[1]).get("proposal_id") : null);
  const [source, setSource] = useState<InvestmentSource>(); const [form, setForm] = useState<InvestmentForm>();
  const [proposal, setProposal] = useState<PackagePreview>(); const [saved, setSaved] = useState<PackagePreview[]>([]);
  const [loading, setLoading] = useState(true); const [pending, setPending] = useState(false); const [reviewed, setReviewed] = useState(false);
  const [error, setError] = useState<string>(); const [notice, setNotice] = useState<string>(); const [attempt, setAttempt] = useState(0);
  const generation = useRef(0); const lock = useRef(false);
  useEffect(() => {
    const current = ++generation.current;
    setLoading(true); setSource(undefined); setForm(undefined); setProposal(undefined); setSaved([]); setError(undefined); setNotice(undefined); setReviewed(false);
    void (async () => {
      try {
        if (mode === "example") {
          const store = exampleStore(window.localStorage); const list = store.list(); const previous = proposalId ? store.get(proposalId) : undefined;
          if (current !== generation.current) return;
          const next = previous?.source ?? exampleSource(); setSource(next); setForm(previous?.input ?? blankForm(next.allocation_run_id)); setProposal(previous); setSaved(list);
        } else {
          if (proposalId) {
            const previous = await loadInvestment(proposalId);
            if (current !== generation.current) return;
            setSource(previous.source); setForm(previous.input); setProposal(previous); return;
          }
          if (!allocationId) return;
          const [next, inputs] = await Promise.all([loadSource(allocationId), loadCatalogForm(allocationId)]); if (current !== generation.current) return;
          setSource(next); setForm(inputs);
        }
      } catch (cause) { if (current === generation.current) setError(cause instanceof Error ? cause.message : "Could not load the saved funding source."); }
      finally { if (current === generation.current) setLoading(false); }
    })();
    return () => { ++generation.current; };
  }, [mode, allocationId, proposalId, attempt]);
  function change(next: InvestmentForm) { setForm(next); setProposal(undefined); setReviewed(false); setError(undefined); setNotice(undefined); }
  function checkInputs(): boolean {
    if (!source || !form) return false;
    const errors = validateInvestment(form, source); setError(errors.length ? errors.join("\n") : undefined);
    setNotice(errors.length ? undefined : "Editor checks passed. Missing project confirmation still makes projects ineligible; the backend validates and calculates on submission.");
    return !errors.length;
  }
  async function calculate() {
    if (!form || lock.current || !checkInputs()) return;
    if (!reviewed) { setError("Review and acknowledge the visible catalog, budget and evaluation assumptions first."); return; }
    lock.current = true; setPending(true);
    const current = generation.current;
    try {
      if (mode === "example") { setProposal(showExample(form)); setNotice("Loaded the fixed synthetic package display. No OR-Tools or capacity engine executed in the browser."); }
      else {
        const result = await createInvestment(form);
        if (current !== generation.current) return;
        setProposal(result); setNotice("Calculated, independently verified and saved for review.");
        window.history.replaceState(null, "", `/investments?${new URLSearchParams({ proposal_id: result.id })}`);
      }
    }
    catch (cause) { if (current !== generation.current) return; setProposal(undefined); setError(cause instanceof FacilityClientError && cause.detail ? [cause.message, ...cause.detail.fields.map((f) => `${f.field}: ${f.message}`)].join("\n") : cause instanceof Error ? cause.message : "Could not calculate the funding package."); }
    finally { lock.current = false; setPending(false); }
  }
  function save() {
    if (!proposal || mode !== "example" || proposal.id !== "frontend-funding-display" || lock.current) return;
    lock.current = true; setPending(true); setError(undefined);
    try {
      const store = exampleStore(window.localStorage); const result = store.save(proposal); setProposal(result); setSaved(store.list());
      window.history.replaceState(null, "", `/investments?${new URLSearchParams({ mode: "example", proposal_id: result.id })}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save the browser funding example."); }
    finally { lock.current = false; setPending(false); }
  }
  function inspectState(state: "needs_inputs" | "no_improvement" | "feasible" | "unknown" | "infeasible") {
    const base = showExample(exampleForm());
    const next: PackagePreview = { ...base, id: `display-${state}`, saved_at: null, solver_status: state === "needs_inputs" ? "not_run" : state === "no_improvement" ? "optimal" : state, plan_outcome: state === "needs_inputs" ? "needs_inputs" : state === "no_improvement" ? "no_improvement" : state === "feasible" ? "improved" : "no_solution", proposed: null, selected_projects: [], total_capital_cost_minor_units: null, total_operating_cost_minor_units: null, total_cost_minor_units: null, remaining_budget_minor_units: null, validation_passed: false, remaining_gap_reasons: ["Hypothetical display state, not an outcome calculated for the edited inputs."] };
    if (state === "needs_inputs") next.candidate_exclusions = [{ candidate_id: "REPAIR-FIVE", reasons: ["Required asset evidence/confirmation missing in this hypothetical state."] }];
    if (state === "no_improvement") { next.proposed = base.source.summary; next.total_capital_cost_minor_units = 0; next.total_operating_cost_minor_units = 0; next.total_cost_minor_units = 0; next.remaining_budget_minor_units = 300000; next.validation_passed = true; next.remaining_gap_reasons.push("An empty or ineligible catalog can leave the entire gap unresolved without making the model infeasible."); }
    if (state === "feasible") { next.proposed = base.proposed; next.selected_projects = base.selected_projects; next.total_capital_cost_minor_units = base.total_capital_cost_minor_units; next.total_operating_cost_minor_units = base.total_operating_cost_minor_units; next.total_cost_minor_units = base.total_cost_minor_units; next.remaining_budget_minor_units = base.remaining_budget_minor_units; next.validation_passed = true; }
    setProposal(next); setNotice("Inspecting a hypothetical solver state. Only the agreed unchanged demo package can be saved in this browser preview.");
  }
  return <div className="space-y-6"><header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-wider text-teal-700">Ministry / Funding review</p><h1 className="mt-2 text-3xl font-bold">Investment package planning</h1><p className="mt-3 text-sm text-slate-600">Saved allocation → remaining gap → reviewed projects → funding package.</p></div><Link className={secondaryClass} href="/allocation">Resource allocation</Link></header>
    {mode === "example" && <div role="note" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><strong>Synthetic funding preview · browser storage only</strong><p className="mt-2">This fixed display example illustrates the agreed repair and commissioning package. No optimizer runs; local saving demonstrates reopening only.</p>{!exercise?.enabled && <Link className="mt-3 inline-block font-semibold underline" href="/investments">Open saved-allocation planning</Link>}</div>}
    {loading && <section role="status" aria-busy="true" className={`${panelClass} p-6`}>Loading frozen allocation source…</section>}
    {error && <div role="alert" className="whitespace-pre-line rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}{!source && <button className={`${secondaryClass} mt-3 block`} onClick={() => setAttempt((value) => value + 1)}>Retry loading</button>}</div>}
    {notice && <p role="status" className="rounded-lg bg-teal-50 p-4 text-sm text-teal-950">{notice}</p>}
    {!loading && !source && !error && <section className={`${panelClass} p-6`}><h2 className="font-semibold">Choose a saved, validated allocation proposal</h2><p className="mt-2 text-sm text-slate-600">Open a saved allocation result with a proposed summary and choose “Plan investments.” Unknown or invalid source proposals cannot establish a funding baseline.</p><Link className={`${buttonClass} mt-4`} href="/allocation">Open allocation planning</Link></section>}
    {!loading && source && form && <>{!source.example && <Link className="inline-block text-sm font-semibold text-teal-800 hover:underline" href={`/allocation?${new URLSearchParams({ proposal_id: source.allocation_run_id })}`}>Reopen source allocation →</Link>}{mode === "example" && <button className={secondaryClass} disabled={pending} onClick={() => change(exampleForm())}>Load agreed synthetic funding inputs and catalog</button>}
      {proposal && <><PackageComparison proposal={proposal} />{mode === "api" && <Link className={secondaryClass} href={`/investments?${new URLSearchParams({ proposal_id: proposal.id })}`}>Reopen saved funding proposal</Link>}</>}
      <details className="rounded-xl border border-slate-200 bg-white p-5"><summary className="cursor-pointer text-sm font-semibold text-teal-800">Inspect the source response plan and remaining gap</summary><div className="mt-4"><SourceSummary source={source} /></div></details>
      <details open={!proposal} className="space-y-4 rounded-xl border border-slate-200 bg-white p-5"><summary className="cursor-pointer text-sm font-semibold text-teal-800">Review or change planning inputs</summary>
      <InvestmentInputs source={source} form={form} change={change} disabled={pending} />
      <section className={`${panelClass} space-y-4 p-5`}><h2 className="text-lg font-semibold">Review before calculation</h2><p className="text-xs text-slate-600">Source demand persists to evaluation; transfers are assumed completed, not executed. No partial project benefits before readiness. The full operating allowance applies, prerequisites are paid for and exclusive alternatives cannot both be selected.</p><label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={reviewed} disabled={pending} onChange={(event) => setReviewed(event.target.checked)} />I reviewed the budget, dates, dependency graph, resource effects, costs, asset evidence and demand assumptions. A proposal authorizes no purchase or budget approval.</label><div className="flex flex-wrap gap-3"><button className={secondaryClass} disabled={pending} onClick={() => checkInputs()}>Check inputs</button><button className={buttonClass} disabled={pending || !reviewed} onClick={calculate}>{mode === "example" ? "Show fixed package example" : "Calculate and save funding proposal"}</button>{mode === "example" && proposal?.id === "frontend-funding-display" && <button className={secondaryClass} disabled={pending} onClick={save}>Save browser funding example for review</button>}</div></section>
      </details>
      {mode === "example" && <details className={`${panelClass} p-5`}><summary className="cursor-pointer text-sm font-semibold text-teal-800">Inspect hypothetical package-result states</summary><p className="mt-3 text-xs text-slate-500">Display examples only; not recomputed outcomes for the current inputs.</p><div className="mt-3 flex flex-wrap gap-2">{([['needs_inputs', 'Incomplete inputs'], ['no_improvement', 'No improvement'], ['feasible', 'Feasible incumbent'], ['unknown', 'Timeout without a plan'], ['infeasible', 'Proven infeasible']] as const).map(([state, title]) => <button key={state} className={secondaryClass} disabled={pending} onClick={() => inspectState(state)}>{title}</button>)}</div></details>}

      {mode === "example" && <section className={`${panelClass} p-5`}><h2 className="text-lg font-semibold">Saved browser funding examples</h2>{!saved.length && <p className="mt-3 text-sm text-slate-500">No funding example saved yet.</p>}<ul className="mt-3 divide-y divide-slate-100">{saved.map((item) => <li className="flex flex-wrap items-center justify-between gap-3 py-3" key={item.id}><p className="text-sm">Repair + commissioning · <Timestamp value={item.saved_at} /></p><Link className={secondaryClass} href={`/investments?${new URLSearchParams({ mode: "example", proposal_id: item.id })}`}>Reopen saved example</Link></li>)}</ul></section>}
    </>}
  </div>;
}
