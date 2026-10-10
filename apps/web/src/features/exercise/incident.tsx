"use client";
import { useState } from "react";
import { createIncidentApiClient } from "../scenarios/api-client";
import { EmergencyAdvicePanel } from "../scenarios/emergency-advice";
import { AssumptionReview } from "../scenarios/review-panel";
import { LoadError, panelClass, secondaryClass } from "../facilities/shared";
import { useExercise, useExerciseNames } from "./context";
import { NextStep, savedId, useSavedResource } from "./journey";

export function BeirutIncident() {
  const exercise = useExercise()!; const names = useExerciseNames();
  const runId = savedId(exercise.links?.scenarios, "run_id");
  const result = useSavedResource(() => createIncidentApiClient().getRun(runId), runId);
  const [report, setReport] = useState(exercise.incident_input?.report_text ?? "");
  const [edit, setEdit] = useState(false);
  const incident = { ...exercise.incident_input!, report_text: report };
  return <div className="space-y-6"><header><p className="text-xs font-semibold uppercase tracking-wider text-teal-700">03 / Understand and respond</p><h1 className="mt-2 text-3xl font-semibold">Beirut emergency assessment</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">Review disrupted care, ask AI for prioritized actions, then compare a response against hospital capacity and transport constraints.</p></header>
    <section className={`${panelClass} p-6`}><div className="flex items-center justify-between gap-3"><h2 className="text-lg font-semibold">Situation report</h2><button className={secondaryClass} onClick={() => setEdit(!edit)}>{edit ? "Finish editing" : "Edit report for AI"}</button></div>{edit ? <label className="mt-4 block text-sm">Report to analyze<textarea className="mt-2 w-full rounded-lg border border-slate-300 p-3 leading-6" rows={6} value={report} onChange={(event) => setReport(event.target.value)} /></label> : <p className="mt-4 text-sm leading-7 text-slate-700">{report}</p>}{report !== exercise.incident_input?.report_text && <p className="mt-3 text-sm text-teal-800">AI will review your edited report. The saved impact and response below still use the original exercise assumptions.</p>}</section>
    <EmergencyAdvicePanel incident={incident} disabled={false} />
    {result.loading && <p role="status">Loading the saved incident impact…</p>}{result.error && <LoadError message={result.error} retry={result.retry} />}
    {result.data && <section className={`${panelClass} p-6`}><h2 className="text-lg font-semibold">What the incident changes</h2><p className="mt-2 text-sm text-slate-500">Saved comparison · simultaneous emergency treatment places</p><div className="mt-5 grid gap-4 md:grid-cols-2">{result.data.rows.map((row) => <article key={row.facility_id} className="rounded-lg border border-slate-200 p-4"><h3 className="font-semibold">{names.hospital(row.facility_id)}</h3><p className="mt-3 text-2xl font-semibold">{row.baseline.estimated_capacity ?? "Unknown"}<span className="mx-3 text-base text-slate-400">→</span>{row.scenario.estimated_capacity ?? "Unknown"}<span className="ml-2 text-xs font-normal text-slate-500">places</span></p><p className="mt-3 text-sm text-slate-600">{row.scenario.status === "unavailable" ? "Service interrupted. Equipment alone cannot reopen it." : row.scenario.estimated_capacity === null ? "Staffing evidence is missing; request a report before including this hospital." : `Limiting resources: ${row.scenario.bottleneck_resource_ids.map(names.resource).join(", ")}.`}</p></article>)}</div><details className="mt-5"><summary className="cursor-pointer text-sm font-medium text-teal-800">Assumptions behind this saved comparison</summary><div className="mt-4"><AssumptionReview input={result.data.input} /></div></details></section>}
    <NextStep to="allocation">Compare the feasible response</NextStep>
  </div>;
}
