"use client";
import { useI18n } from "@/lib/i18n/context";

import { useState } from "react";
import { createIncidentApiClient } from "../scenarios/api-client";
import { EmergencyAdvicePanel } from "../scenarios/emergency-advice";
import { AssumptionReview } from "../scenarios/review-panel";
import { LoadError, panelClass, secondaryClass } from "../facilities/shared";
import { useExercise, useExerciseNames } from "./context";
import { NextStep, savedId, useSavedResource } from "./journey";
import { PageHeader } from "./page-header";

export function BeirutIncident() {
  const { t } = useI18n();
  const exercise = useExercise()!; const names = useExerciseNames();
  const runId = savedId(exercise.links?.scenarios, "run_id");
  const result = useSavedResource(() => createIncidentApiClient().getRun(runId), runId);
  const [report, setReport] = useState(exercise.incident_input?.report_text ?? "");
  const [edit, setEdit] = useState(false);
  const incident = { ...exercise.incident_input!, report_text: report };
  return <div className="space-y-4">
    <PageHeader title={t("Incident assessment")} description={t("Hospital impact and AI response recommendations.")} />
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(340px,0.85fr)]">
      <div className="space-y-4">
        <section className={`${panelClass} p-5`}><div className="flex items-center justify-between gap-3"><h2 className="font-semibold">{t("Situation report")}</h2><button className={secondaryClass} onClick={() => setEdit(!edit)}>{t(edit ? "Done editing" : "Edit report")}</button></div>
          {edit ? <label className="mt-3 block text-sm">{t("AI input")}<textarea className="mt-2 w-full rounded-lg border border-slate-300 p-3 leading-6" rows={6} value={report} onChange={(event) => setReport(event.target.value)} /></label> : <details className="mt-3"><summary className="cursor-pointer text-sm text-teal-800">{t("Read the Beirut incident report")}</summary><p className="mt-3 text-sm leading-6 text-slate-700">{t(report)}</p></details>}
          {report !== exercise.incident_input?.report_text && <p className="mt-3 text-xs text-teal-800">{t("Edited AI input · impact below uses the saved exercise.")}</p>}
        </section>
        {result.loading && <p role="status">{t("Loading incident impact…")}</p>}{result.error && <LoadError message={result.error} retry={result.retry} />}
        {result.data && <section className={`${panelClass} overflow-hidden`}><div className="border-b border-slate-100 px-5 py-4"><h2 className="font-semibold">{t("Hospital impact")}</h2><p className="mt-1 text-xs text-slate-500">{t("Before → incident · modeled simultaneous treatment places")}</p></div><ul className="divide-y divide-slate-100">{result.data.rows.map((row) => <li key={row.facility_id} className="px-5 py-4"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">{t(names.hospital(row.facility_id))}</h3><p className="rounded-lg bg-slate-50 px-3 py-2 text-2xl metric-number">{t(row.baseline.estimated_capacity ?? "Unknown")}<span className="mx-2 text-sm text-slate-400">→</span>{t(row.scenario.estimated_capacity ?? "Unknown")}</p></div><p className="mt-1 text-xs leading-5 text-slate-500">{t(row.scenario.status === "unavailable" ? "Service interrupted" : row.scenario.estimated_capacity === null ? "Staff report missing" : `Limits: ${row.scenario.bottleneck_resource_ids.map(names.resource).join(", ")}`)}</p></li>)}</ul><details className="border-t border-slate-100 p-5"><summary className="cursor-pointer text-sm font-medium text-teal-800">{t("Saved assumptions")}</summary><div className="mt-3"><AssumptionReview input={result.data.input} /></div></details></section>}
      </div>
      <div className="xl:sticky xl:top-20"><EmergencyAdvicePanel incident={incident} disabled={false} /></div>
    </div>
    <NextStep to="allocation">{t("Compare response plan")}</NextStep>
  </div>;
}
