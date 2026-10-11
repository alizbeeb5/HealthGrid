"use client";
import type { Locale } from "@/lib/i18n/translate";
import { useI18n } from "@/lib/i18n/context";

import { useExerciseNames, useExercise } from "../exercise/context";
import { useEffect, useRef, useState } from "react";
import type { components } from "../../lib/api/schema";
import { buttonClass, panelClass, Timestamp } from "../facilities/shared";
import type { IncidentFields } from "./model";
import type { ComponentState } from "./review-panel";

export type EmergencyAdvice = components["schemas"]["EmergencyAdviceResponse"];

export async function requestEmergencyAdvice(incident: IncidentFields, locale: Locale = "en"): Promise<EmergencyAdvice> {
  let response: Response;
  try {
    response = await fetch("/api/v1/intelligence/incidents/advice", {
      method: "POST", cache: "no-store", headers: { "Content-Type": "application/json", "Accept-Language": locale },
      body: JSON.stringify({ incident: { ...incident, title: incident.title.trim() || "Incident report" } }),
    });
  } catch { throw new Error("Could not reach emergency guidance. Your incident is unchanged."); }
  if (!response.ok) {
    let fields: { field: string; message: string }[] = [];
    if (response.status === 422) {
      try {
        const body = await response.json();
        if (Array.isArray(body?.error?.fields)) fields = body.error.fields;
      } catch { /* Keep the status-specific message if the error body is unreadable. */ }
    }
    throw new Error(response.status === 422
      ? ["Check the report and incident fields before requesting guidance.", ...fields.map((item) => `${item.field}: ${item.message}`)].join("\n")
      : "Emergency guidance is unavailable. Your incident is unchanged.");
  }
  try { return await response.json() as EmergencyAdvice; }
  catch { throw new Error("Emergency guidance returned an unreadable response."); }
}

export function EmergencyAdviceResult({ data }: { data: EmergencyAdvice }) {
  const { t } = useI18n();
  const names = useExerciseNames();
  return <div className="space-y-4">
    <p role="status" className="text-sm">{t(data.advice_status === "completed" ? data.proposal?.summary : data.advice_status === "unavailable" ? "Emergency guidance is unavailable. Configure the server API key or continue manually." : data.advice_status === "refused" ? "The model declined this request. Continue manually." : "The guidance request failed. Try again or continue manually.")}</p>
    {data.proposal && <><ol className="space-y-3">{data.proposal.actions.map((action, i) => <li key={i} className="rounded-lg border border-slate-200 p-4">
      <p className="text-xs font-semibold uppercase text-teal-700">{t(action.priority === "immediate" ? "First steps" : "Follow-up")} · {t(action.facility_ids.map(names.hospital).join(", ") || "Network coordination")}</p>
      <h3 className="mt-1 font-semibold">{t(i + 1)}. {t(action.title)}</h3>
      <ul className="mt-2 list-disc space-y-1 ps-5 text-sm">{action.steps.map((step, j) => <li key={j}>{t(step)}</li>)}</ul>
      <p className="mt-3 text-sm text-slate-600">{t("Why: ")}{t(action.rationale)}</p>
      <p className="mt-3 text-xs font-semibold">{t("Verify before acting")}</p><ul className="mt-1 list-disc space-y-1 ps-5 text-xs">{action.prerequisites.map((item, j) => <li key={j}>{t(item)}</li>)}</ul>
      <details className="mt-3 text-xs"><summary className="cursor-pointer font-medium">{t("Supporting report and hospital data")}</summary><ul className="mt-2 space-y-2">{action.evidence_paths.map((path) => <li key={path}><span className="break-all font-medium">{t(path)}</span>: {t(String(data.evidence.find((item) => item.path === path)?.value ?? "Unknown (null)"))}</li>)}</ul></details>
    </li>)}</ol>{data.proposal.questions.length > 0 && <div><h3 className="text-sm font-semibold">{t("Information needed")}</h3><ul className="mt-2 list-disc space-y-1 ps-5 text-sm">{data.proposal.questions.map((question, i) => <li key={i}>{t(question)}</li>)}</ul></div>}</>}
    <details className="text-xs text-slate-500"><summary className="cursor-pointer">{t("Sources, limitations and model details")}</summary><ul className="mt-3 space-y-1">{data.warnings.map((warning, i) => <li key={i}>{t(warning)}</li>)}</ul>
    <p className="text-xs text-slate-500">{t("Model: ")}{t(data.model ?? "Not supplied")} · {t(data.elapsed_ms)}{t(" ms · Hospital data as of ")}<Timestamp value={data.as_of} /></p></details>
  </div>;
}

export function EmergencyAdvicePanel({ incident, disabled }: { incident: IncidentFields; disabled: boolean }) {
  const { t, locale } = useI18n();
  const exercise = useExercise();
  const [state, setState] = useState<ComponentState<EmergencyAdvice>>({ phase: "idle" });
  const generation = useRef(0);
  const input = JSON.stringify(incident);
  useEffect(() => { ++generation.current; setState({ phase: "idle" }); return () => { ++generation.current; }; }, [input, locale]);
  async function request() {
    const current = ++generation.current;
    setState({ phase: "loading" });
    try {
      const data = await requestEmergencyAdvice(incident, locale);
      if (current === generation.current) setState({ phase: "ready", data });
    } catch (error) {
      if (current === generation.current) setState({ phase: "error", message: error instanceof Error ? error.message : "Guidance failed." });
    }
  }
  return <section className={`${panelClass} space-y-4 p-5`}>
    <h2 className="text-lg font-semibold">{t("AI response recommendations")}</h2>
    <p className="text-sm text-slate-600">{t("Prioritized actions from the incident report and hospital evidence.")}</p>
    <button className={buttonClass} disabled={disabled || !incident.report_text?.trim() || state.phase === "loading"} onClick={() => void request()}>{t(state.phase === "loading" ? "Preparing next steps…" : "Generate recommendations · live AI")}</button>
    {state.phase === "idle" && <p className="text-xs text-slate-500">{t(exercise?.enabled ? "Ready to analyze · uses the configured server-side AI key." : "Add a situation report to begin. Editing it clears previous guidance.")}</p>}
    {state.phase === "loading" && <p role="status" className="text-sm">{t("Reviewing the report and hospital evidence…")}</p>}
    {state.phase === "error" && <p role="alert" className="whitespace-pre-line text-sm text-rose-800">{t(state.message)}</p>}
    {state.phase === "ready" && <EmergencyAdviceResult data={state.data} />}
  </section>;
}
