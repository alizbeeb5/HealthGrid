"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { money } from "../allocation/model";
import { createInvestment, loadInvestment } from "../investments/source";
import { validateInvestment, type PackagePreview } from "../investments/model";
import { buttonClass, LoadError, panelClass, Timestamp } from "../facilities/shared";
import { useExercise, useExerciseNames } from "./context";
import { NextStep, savedId, useSavedResource } from "./journey";

export function BeirutFunding() {
  const exercise = useExercise()!; const names = useExerciseNames(); const params = useSearchParams();
  const originalId = savedId(exercise.links?.investments, "proposal_id");
  const id = params.get("proposal_id") ?? originalId;
  const loaded = useSavedResource(() => loadInvestment(id), id);
  const [proposal, setProposal] = useState<PackagePreview>();
  const [budget, setBudget] = useState(""); const [selected, setSelected] = useState<string[]>([]);
  const [pending, setPending] = useState(false); const [error, setError] = useState<string>(); const lock = useRef(false);
  useEffect(() => { if (loaded.data) { setProposal(loaded.data); setBudget(String(Number(loaded.data.input.budget_minor_units) / 100)); setSelected(loaded.data.input.candidates.map((c) => c.candidate_id)); } }, [loaded.data]);
  async function compare() {
    if (!loaded.data || lock.current) return;
    setError(undefined);
    if (!/^\d+(\.\d{1,2})?$/.test(budget)) { setError("Enter a budget in dollars, with at most two decimal places."); return; }
    const input = { ...loaded.data.input, budget_minor_units: String(Math.round(Number(budget) * 100)), candidates: loaded.data.input.candidates.filter((c) => selected.includes(c.candidate_id)) };
    const errors = validateInvestment(input, loaded.data.source);
    if (errors.length) { setError(errors.join("\n")); return; }
    lock.current = true; setPending(true);
    try { const result = await createInvestment(input); setProposal(result); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not calculate this package."); }
    finally { lock.current = false; setPending(false); }
  }
  const dirty = proposal && (Math.round(Number(budget) * 100) !== Number(proposal.input.budget_minor_units) || [...selected].sort().join(",") !== proposal.input.candidates.map((c) => c.candidate_id).sort().join(","));
  const valid = proposal?.validation_passed && proposal.proposed && ["optimal", "feasible"].includes(proposal.solver_status);
  return <div className="space-y-6"><header><p className="text-xs font-semibold uppercase tracking-wider text-teal-700">05 / Invest in the remaining gap</p><h1 className="mt-2 text-3xl font-semibold">What should we fund?</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">The transfer addresses the immediate monitor shortage. Recovery funding compares equipment repairs and confirmed staffing coverage for 11 August.</p></header>
    {loaded.loading && <p role="status">Loading the recovery package…</p>}{loaded.error && <LoadError message={loaded.error} retry={loaded.retry} />}
    {proposal && <>
      <section className="grid gap-4 sm:grid-cols-3">{[["Gap after the immediate response", `${proposal.source.summary.unmet_service_places} places`], ["Supported after this funding package", valid ? `${proposal.proposed!.covered_service_places} places` : "No validated package"], ["Remaining gap", valid ? `${proposal.proposed!.unmet_service_places} places` : "Not determined"]].map(([label, value]) => <div className={`${panelClass} p-6`} key={label}><p className="text-xs text-slate-500">{label}</p><p className="mt-3 text-2xl font-semibold">{value}</p></div>)}</section>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className={`${panelClass} space-y-5 p-6`}><h2 className="text-xl font-semibold">{valid ? "Recommended package" : "Package needs review"}</h2>{valid ? <><div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-3xl font-semibold text-teal-900">{money(proposal.total_cost_minor_units!)}</p><p className="mt-2 text-sm text-slate-500">{money(proposal.total_capital_cost_minor_units!)} setup + {money(proposal.total_operating_cost_minor_units!)} operating allowance</p></div><p className="text-sm text-slate-600">{money(proposal.remaining_budget_minor_units!)} budget remaining</p></div><div className="space-y-4">{proposal.selected_projects.map((project) => { const candidate = proposal.input.candidates.find((c) => c.candidate_id === project.candidate_id); return <article className="rounded-lg border border-teal-200 bg-teal-50/40 p-5" key={project.candidate_id}><h3 className="font-semibold">{candidate?.name ?? project.candidate_id}</h3><p className="mt-2 text-sm text-slate-600">{candidate ? names.hospital(candidate.facility_id) : "Selected hospital"}</p><p className="mt-3 text-sm">{project.resource_effects.map((effect) => `+${effect.quantity_delta} ${names.resource(effect.resource_id)}`).join(" · ")}</p><p className="mt-3 text-sm font-medium">{money(project.total_cost_minor_units)} · Ready <Timestamp value={project.ready_at} /></p></article>; })}{!proposal.selected_projects.length && <p className="text-sm">No project improves coverage within the reviewed constraints.</p>}</div></> : <p className="text-sm text-slate-600">{proposal.remaining_gap_reasons.join(" ") || "No feasible package was returned for these inputs."}</p>}
          <p className="text-xs leading-5 text-slate-500">Includes {proposal.input.operating_cost_months} month(s) of operating cost. The earlier {money(proposal.source.transfer_cost_minor_units)} transfer is separate. Staffing availability is a reviewed assumption.</p>
          {proposal.id !== originalId && <p className="rounded-lg bg-slate-50 p-3 text-sm">Alternative saved for comparison. Outcome rehearsal continues to use the original exercise package. <Link className="font-medium text-teal-800 underline" href={`/investments?proposal_id=${encodeURIComponent(proposal.id)}`}>Reopen this saved comparison</Link></p>}
          <details><summary className="cursor-pointer text-sm font-medium text-teal-800">Hospital effects and calculation evidence</summary><div className="mt-4 overflow-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Hospital</th><th className="p-2">Capacity before</th><th className="p-2">After funding</th></tr></thead><tbody>{proposal.source.summary.rows.map((row) => <tr key={row.facility_id} className="border-t"><td className="p-2">{names.hospital(row.facility_id)}</td><td className="p-2">{row.estimated_capacity ?? "Unknown"}</td><td className="p-2">{valid ? proposal.proposed!.rows.find((r) => r.facility_id === row.facility_id)?.estimated_capacity ?? "Unknown" : "Not determined"}</td></tr>)}</tbody></table></div><p className="mt-3 text-xs text-slate-500">{proposal.solver_status} · {proposal.validation_passed ? "Constraints independently verified" : "Verification not passed"}</p><ul className="mt-3 space-y-2 text-xs">{proposal.remaining_gap_reasons.map((r) => <li key={r}>{r}</li>)}{proposal.candidate_exclusions.map((r) => <li key={r.candidate_id}>{r.reasons.join("; ")}</li>)}</ul><p className="mt-3 text-xs">Evaluation: <Timestamp value={proposal.input.evaluation_at} /></p></details>
        </section>
        <section className={`${panelClass} space-y-5 p-6`}><h2 className="text-lg font-semibold">Compare a different budget</h2><label className="block text-sm font-medium">Available funding (USD)<input type="number" min="0" step="0.01" className="mt-2 w-full rounded-lg border border-slate-300 p-3" value={budget} onChange={(event) => setBudget(event.target.value)} disabled={pending} /></label><fieldset disabled={pending}><legend className="mb-3 text-sm font-medium">Projects to consider</legend><div className="space-y-3">{loaded.data?.input.candidates.map((candidate) => <label className="flex items-start gap-3 text-sm" key={candidate.candidate_id}><input className="mt-1" type="checkbox" checked={selected.includes(candidate.candidate_id)} onChange={(event) => setSelected(event.target.checked ? [...selected, candidate.candidate_id] : selected.filter((value) => value !== candidate.candidate_id))} /><span>{candidate.name}<span className="mt-1 block text-xs text-slate-500">{money(Number(candidate.capital_cost_minor_units))} setup · {money(Number(candidate.monthly_operating_cost_minor_units))}/month</span></span></label>)}</div></fieldset><p className="text-xs leading-5 text-slate-500">The solver selects the combination that covers the most planned demand within your budget. Selecting a candidate makes it eligible; it does not force funding.</p>{dirty && <p role="status" className="text-sm text-slate-600">Inputs changed. The displayed result is the last saved package; compare again to apply these choices.</p>}<button className={buttonClass} disabled={pending} onClick={compare}>{pending ? "Comparing packages…" : "Compare funding options"}</button>{error && <p role="alert" className="whitespace-pre-line text-sm text-rose-800">{error}</p>}</section>
      </div>
    </>}
    <NextStep to="decisions">Track implementation and outcomes</NextStep>
  </div>;
}
