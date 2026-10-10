"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { getDecisionRecord, getReview, listReviews, presentDecision } from "../decisions/source";
import type { OutcomeReview } from "../decisions/model";
import { OutcomePanel } from "../decisions/outcome-panel";
import { LoadError, panelClass, secondaryClass, Timestamp } from "../facilities/shared";
import { useExercise, useExerciseNames } from "./context";
import { useSavedResource } from "./journey";
import { ExerciseAdvance } from "./navigation";

export function BeirutOutcomes() {
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
  return <div className="space-y-6"><header><p className="text-xs font-semibold uppercase tracking-wider text-teal-700">06 / Follow through</p><h1 className="mt-2 text-3xl font-semibold">Did the response restore capacity?</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">Track the two exercise decisions, receive follow-up reports, and compare the expected result with reported capacity.</p></header>
    {loaded.loading && <p role="status">Loading decisions and evidence…</p>}{loaded.error && <LoadError message={loaded.error} retry={loaded.retry} />}
    {loaded.data && <section className="grid gap-4 md:grid-cols-2">{loaded.data.decisions.map((decision, index) => <article className={`${panelClass} p-6`} key={decision.decision_id}><div className="flex items-start justify-between gap-3"><p className="text-xs font-semibold uppercase tracking-wide text-teal-700">{index === 0 ? "Immediate response" : "Recovery funding"}</p><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium">{decision.status === "completed" ? "Completion reported" : decision.status === "draft" ? "Ready for review" : decision.status.replaceAll("_", " ")}</span></div><h2 className="mt-3 text-lg font-semibold">{decision.title}</h2><p className="mt-3 text-sm text-slate-600">{decision.rationale}</p><p className="mt-4 text-xs text-slate-500">{decision.owner_name} · Target <Timestamp value={decision.target_completion_at} /></p><details className="mt-4"><summary className="cursor-pointer text-sm font-medium text-teal-800">Action progress and recorded events</summary><ul className="mt-3 space-y-3 text-sm">{decision.actions.map((action) => <li key={action.action_id}>{action.title}<span className="block text-xs text-slate-500">{action.status.replaceAll("_", " ")}</span></li>)}</ul><ol className="mt-4 space-y-2 text-xs text-slate-500">{decision.events.map((event) => <li key={event.event_id}>{event.type.replaceAll("_", " ")} · <Timestamp value={event.recorded_at} /><p>{event.note}</p></li>)}</ol></details></article>)}</section>}
    <ExerciseAdvance />
    {review ? <section className={`${panelClass} space-y-5 p-6`}><div><h2 className="text-xl font-semibold">Expected versus reported capacity</h2><p className="mt-2 text-sm text-slate-500">Only fresh reports can support the result. A completed action alone is not outcome evidence.</p></div><div className="flex flex-wrap gap-3">{loaded.data?.reviews.map((item) => <button className={`${secondaryClass} ${review.review_id === item.review_id ? "border-teal-700 bg-teal-50 text-teal-900" : ""}`} aria-pressed={review.review_id === item.review_id} key={item.review_id} onClick={() => setChoice(item.review_id)}>{item.review_id === exercise.missing_review_id ? "Before fresh reports" : item.review_id === exercise.supported_review_id ? "After fresh reports" : "Saved follow-up review"}</button>)}</div><div className="grid gap-4 md:grid-cols-3">{review.rows.map((row) => <article key={row.facility_id} className="rounded-lg border border-slate-200 p-5"><h3 className="text-sm font-semibold">{names.hospital(row.facility_id)}</h3><div className="mt-4 grid grid-cols-2 gap-3"><div><p className="text-xs text-slate-500">Expected</p><p className="mt-2 text-2xl font-semibold">{row.expected ?? "Unknown"}</p></div><div><p className="text-xs text-slate-500">Reported estimate</p><p className="mt-2 text-2xl font-semibold">{row.observed ?? "Unknown"}</p></div></div><p className={`mt-4 text-sm font-medium ${row.classification === "at_or_above_expected" ? "text-teal-800" : "text-amber-800"}`}>{labels[row.classification]}</p></article>)}</div><p className="text-xs text-slate-500">Simultaneous treatment places · Captured <Timestamp value={review.captured_at} /> · Included hospitals only</p><details><summary className="cursor-pointer text-sm font-medium text-teal-800">Inspect the retained evidence and exclusions</summary><div className="mt-4"><OutcomePanel review={review} /></div></details></section> : !loaded.loading && <section className={`${panelClass} p-6`}><h2 className="text-lg font-semibold">Follow-up evidence has not arrived yet</h2><p className="mt-2 text-sm leading-6 text-slate-600">Complete the transfer rehearsal, then the recovery rehearsal above. Two saved reviews will show how fresh reports change what we can conclude.</p></section>}
  </div>;
}
