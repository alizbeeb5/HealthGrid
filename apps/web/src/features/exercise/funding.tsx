"use client";
import { MetricCard } from "@/components/metric-card";
import { useI18n } from "@/lib/i18n/context";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { money } from "../allocation/model";
import { createInvestment, loadInvestment } from "../investments/source";
import { validateInvestment, type PackagePreview } from "../investments/model";
import { buttonClass, LoadError, panelClass, Timestamp } from "../facilities/shared";
import { useExercise, useExerciseNames } from "./context";
import { PageHeader } from "./page-header";
import { NextStep, savedId, useSavedResource } from "./journey";

export function BeirutFunding() {
  const { t } = useI18n();
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
  return <div className="space-y-4"><PageHeader title={t("Recovery funding")} description={t("Compare projects that close the remaining gap by 11 August.")} />
    {loaded.loading && <p role="status">{t("Loading the recovery package…")}</p>}{loaded.error && <LoadError message={loaded.error} retry={loaded.retry} />}
    {proposal && <>
      <section className="grid gap-4 sm:grid-cols-3">
        <MetricCard label="Gap after response" value={`${proposal.source.summary.unmet_service_places} places`} tone={proposal.source.summary.unmet_service_places > 0 ? "gap" : "capacity"} />
        <MetricCard label="Coverage after funding" value={valid ? `${proposal.proposed!.covered_service_places} places` : "No validated package"} tone={valid ? "capacity" : "neutral"} />
        <MetricCard label="Remaining gap" value={valid ? `${proposal.proposed!.unmet_service_places} places` : "Not determined"} tone={valid ? proposal.proposed!.unmet_service_places > 0 ? "gap" : "capacity" : "neutral"} />
      </section>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className={`${panelClass} space-y-5 p-6`}><h2 className="text-xl font-semibold">{t(valid ? "Recommended package" : "Package needs review")}</h2>{valid ? <><div className="flex flex-wrap items-end justify-between gap-4"><div><p className="metric-value rounded-lg bg-blue-50 px-4 py-3 text-blue-950">{t(money(proposal.total_cost_minor_units!))}</p><p className="mt-2 text-sm text-slate-500">{t(money(proposal.total_capital_cost_minor_units!))}{t(" setup + ")}{t(money(proposal.total_operating_cost_minor_units!))}{t(" operating allowance")}</p></div><p className="text-sm text-slate-600">{t(money(proposal.remaining_budget_minor_units!))}{t(" budget remaining")}</p></div><div className="space-y-4">{proposal.selected_projects.map((project) => { const candidate = proposal.input.candidates.find((c) => c.candidate_id === project.candidate_id); return <article className="rounded-lg border border-teal-200 bg-teal-50/40 p-5" key={project.candidate_id}><h3 className="font-semibold">{t(candidate?.name ?? project.candidate_id)}</h3><p className="mt-2 text-sm text-slate-600">{t(candidate ? names.hospital(candidate.facility_id) : "Selected hospital")}</p><p className="mt-3 text-sm">{t(project.resource_effects.map((effect) => `+${effect.quantity_delta} ${names.resource(effect.resource_id)}`).join(" · "))}</p><p className="mt-3 text-sm font-medium">{t(money(project.total_cost_minor_units))}{t(" · Ready ")}<Timestamp value={project.ready_at} /></p></article>; })}{!proposal.selected_projects.length && <p className="text-sm">{t("No project improves coverage within the reviewed constraints.")}</p>}</div></> : <p className="text-sm text-slate-600">{t(proposal.remaining_gap_reasons.join(" ") || "No feasible package was returned for these inputs.")}</p>}
          <p className="text-xs leading-5 text-slate-500">{t(proposal.input.operating_cost_months)}{t(" month(s) of operating allowance · ")}{t(money(proposal.source.transfer_cost_minor_units))}{t(" transfer cost excluded · Assumes confirmed staff availability.")}</p>
          {proposal.id !== originalId && <p className="rounded-lg bg-slate-50 p-3 text-sm">{t("Alternative comparison. Rehearsal uses the original package. ")}<Link className="font-medium text-teal-800 underline" href={`/investments?proposal_id=${encodeURIComponent(proposal.id)}`}>{t("Reopen this saved comparison")}</Link></p>}
          <details><summary className="cursor-pointer text-sm font-medium text-teal-800">{t("Hospital effects and calculation evidence")}</summary><div className="mt-4 overflow-auto"><table className="w-full text-start text-sm"><thead><tr><th className="p-2">{t("Hospital")}</th><th className="p-2">{t("Capacity before")}</th><th className="p-2">{t("After funding")}</th></tr></thead><tbody>{proposal.source.summary.rows.map((row) => <tr key={row.facility_id} className="border-t"><td className="p-2">{t(names.hospital(row.facility_id))}</td><td className="p-2">{t(row.estimated_capacity ?? "Unknown")}</td><td className="p-2">{t(valid ? proposal.proposed!.rows.find((r) => r.facility_id === row.facility_id)?.estimated_capacity ?? "Unknown" : "Not determined")}</td></tr>)}</tbody></table></div><p className="mt-3 text-xs text-slate-500">{t(proposal.solver_status)} · {t(proposal.validation_passed ? "Constraints independently verified" : "Verification not passed")}</p><ul className="mt-3 space-y-2 text-xs">{proposal.remaining_gap_reasons.map((r) => <li key={r}>{t(r)}</li>)}{proposal.candidate_exclusions.map((r) => <li key={r.candidate_id}>{t(r.reasons.join("; "))}</li>)}</ul><p className="mt-3 text-xs">{t("Evaluation: ")}<Timestamp value={proposal.input.evaluation_at} /></p></details>
        </section>
        <section className={`${panelClass} space-y-4 p-5 lg:sticky lg:top-20`}><h2 className="text-lg font-semibold">{t("Budget comparison")}</h2><label className="block text-sm font-medium">{t("Budget (USD)")}<input type="number" min="0" step="0.01" className="mt-2 w-full rounded-lg border border-slate-300 p-3" value={budget} onChange={(event) => setBudget(event.target.value)} disabled={pending} /></label><fieldset disabled={pending}><legend className="mb-3 text-sm font-medium">{t("Eligible projects")}</legend><div className="space-y-3">{loaded.data?.input.candidates.map((candidate) => <label className="flex items-start gap-3 text-sm" key={candidate.candidate_id}><input className="mt-1" type="checkbox" checked={selected.includes(candidate.candidate_id)} onChange={(event) => setSelected(event.target.checked ? [...selected, candidate.candidate_id] : selected.filter((value) => value !== candidate.candidate_id))} /><span>{t(candidate.name)}<span className="mt-1 block text-xs text-slate-500">{t(money(Number(candidate.capital_cost_minor_units)))}{t(" setup · ")}{t(money(Number(candidate.monthly_operating_cost_minor_units)))}{t("/month")}</span></span></label>)}</div></fieldset><p className="text-xs leading-5 text-slate-500">{t("Choose eligible projects; the solver selects the best package within budget.")}</p>{dirty && <p role="status" className="text-sm text-slate-600">{t("Inputs changed — compare to update the result.")}</p>}<button className={buttonClass} disabled={pending} onClick={compare}>{t(pending ? "Comparing packages…" : "Compare funding options")}</button>{error && <p role="alert" className="whitespace-pre-line text-sm text-rose-800">{t(error)}</p>}</section>
      </div>
    </>}
    <NextStep to="decisions">{t("Track implementation and outcomes")}</NextStep>
  </div>;
}
