"use client";
import { useI18n } from "@/lib/i18n/context";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { getDecisionRecord, getReview, listReviews, presentDecision } from "../decisions/source";
import type { OutcomeReview } from "../decisions/model";
import { OutcomePanel } from "../decisions/outcome-panel";
import { LoadError, panelClass, secondaryClass, Timestamp } from "../facilities/shared";
import { useExercise, useExerciseNames } from "./context";
import { useSavedResource } from "./journey";
import { PageHeader } from "./page-header";
import { ExerciseAdvance } from "./navigation";

export function BeirutOutcomes() {
  const { t } = useI18n();
  const exercise = useExercise()!; const names = useExerciseNames(); const params = useSearchParams();
  const [choice, setChoice] = useState<string>();
  const loaded = useSavedResource(async () => {
    const wire = await Promise.all([getDecisionRecord(exercise.allocation_decision_id!), getDecisionRecord(exercise.investment_decision_id!)]);
    const reviews = await listReviews(exercise.investment_decision_id!);
    const requested = params.get("review_id");
    if (requested && !reviews.some((r) => r.review_id === requested)) reviews.push(await getReview(exercise.investment_decision_id!, requested));
    return { decisions: wire.map((d) => presentDecision(d, wire)), reviews };
  }, `${exercise.phase}:${params.get("review_id") ?? ""}`);
  const selected = choice ?? params.get("review_id") ?? exercise.supported_review_id;
  const review = loaded.data?.reviews.find((r) => r.review_id === selected) ?? loaded.data?.reviews[0];
  const labels: Record<OutcomeReview["rows"][number]["classification"], string> = { at_or_above_expected: "Expected capacity supported", below_expected: "Capacity still below target", insufficient_evidence: "Fresh reports needed", too_early: "Before the evaluation date", not_comparable: "Cannot compare yet" };
  return <div className="space-y-4">
    <PageHeader title={t("Outcomes")} description={t("Expected capacity compared with follow-up reports.")} />
    {loaded.loading && <p role="status">{t("Loading decisions and evidence…")}</p>}
    {loaded.error && <LoadError message={loaded.error} retry={loaded.retry} />}
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div>
        {review ? <section className={`${panelClass} space-y-4 p-5`}>
          <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">{t("Capacity comparison")}</h2><div role="group" aria-label={t("Outcome evidence")} className="flex flex-wrap gap-2">{loaded.data?.reviews.map((item) => <button className={`${secondaryClass} ${review.review_id === item.review_id ? "border-teal-700 bg-teal-50 text-teal-900" : ""}`} aria-pressed={review.review_id === item.review_id} key={item.review_id} onClick={() => setChoice(item.review_id)}>{t(item.review_id === exercise.missing_review_id ? "Before reports" : item.review_id === exercise.supported_review_id ? "After reports" : "Saved review")}</button>)}</div></div>
          <div className="overflow-x-auto"><table className="w-full text-start text-sm"><caption className="sr-only">{t("Expected and reported capacity at included hospitals")}</caption><thead className="border-y border-slate-200 bg-slate-50"><tr>{["Hospital", "Expected", "Reported", "Evidence"].map((title) => <th key={title} scope="col" className="px-3 py-3 text-xs font-medium text-slate-500">{t(title)}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{review.rows.map((row) => <tr key={row.facility_id}><th scope="row" className="px-3 py-4 font-medium">{t(names.hospital(row.facility_id))}</th><td className="px-3 py-4 text-xl metric-number">{t(row.expected ?? "Unknown")}</td><td className={`px-3 py-4 text-2xl metric-number ${row.observed === null ? "text-slate-500" : row.classification === "at_or_above_expected" ? "bg-teal-50 text-teal-950" : row.classification === "below_expected" ? "bg-rose-50 text-rose-950" : "text-slate-700"}`}>{t(row.observed ?? "Unknown")}</td><td className={`px-3 py-4 text-xs font-medium ${row.classification === "at_or_above_expected" ? "text-teal-800" : "text-amber-800"}`}>{t(labels[row.classification])}</td></tr>)}</tbody></table></div>
          <p className="text-xs text-slate-500">{t("Simultaneous treatment places · Captured ")}<Timestamp value={review.captured_at} />{t(" · Included hospitals")}</p>
          <details><summary className="cursor-pointer text-sm font-medium text-teal-800">{t("Sources and excluded hospitals")}</summary><div className="mt-4"><OutcomePanel review={review} /></div></details>
        </section> : !loaded.loading && !loaded.error && <section className={`${panelClass} p-6`}><h2 className="text-lg font-semibold">{t("Awaiting follow-up reports")}</h2><p className="mt-2 text-sm text-slate-500">{t("Run the transfer and recovery simulations to capture outcome evidence.")}</p></section>}
      </div>
      <div className="space-y-4 xl:sticky xl:top-20">
        <ExerciseAdvance />
        {loaded.data && <section className={`${panelClass} overflow-hidden`}><h2 className="border-b border-slate-100 px-5 py-4 font-semibold">{t("Decision progress")}</h2><div className="divide-y divide-slate-100">{loaded.data.decisions.map((decision, index) => <article className="p-5" key={decision.decision_id}><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-semibold text-teal-700">{t(index === 0 ? "Immediate response" : "Recovery funding")}</p><span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-medium">{t(decision.status === "completed" ? "Completion reported" : decision.status === "draft" ? "Ready for review" : decision.status.replaceAll("_", " "))}</span></div><h3 className="mt-3 text-sm font-semibold">{t(decision.title)}</h3><p className="mt-3 text-xs text-slate-500">{t(decision.owner_name)}</p><p className="mt-1 text-xs text-slate-500">{t("Target ")}<Timestamp value={decision.target_completion_at} /></p><details className="mt-3"><summary className="cursor-pointer text-xs font-medium text-teal-800">{t("Actions and timeline")}</summary><p className="mt-3 text-xs text-slate-500">{t(decision.rationale)}</p><ul className="mt-3 space-y-3 text-xs">{decision.actions.map((action) => <li key={action.action_id}>{t(action.title)}<span className="mt-1 block text-slate-500">{t(action.status.replaceAll("_", " "))}</span></li>)}</ul><ol className="mt-4 space-y-2 text-xs text-slate-500">{decision.events.map((event) => <li key={event.event_id}>{t(event.type.replaceAll("_", " "))} · <Timestamp value={event.recorded_at} /><p>{t(event.note)}</p></li>)}</ol></details></article>)}</div></section>}
      </div>
    </div>
  </div>;
}
