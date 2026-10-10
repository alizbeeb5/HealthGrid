"use client";

import { useEffect, useRef, useState } from "react";
import type { components } from "../../lib/api/schema";
import { secondaryClass, panelClass, Timestamp } from "../facilities/shared";
import type { IncidentFields } from "./model";
import type { ComponentState } from "./review-panel";

export type EmergencyAdvice = components["schemas"]["EmergencyAdviceResponse"];

export async function requestEmergencyAdvice(incident: IncidentFields): Promise<EmergencyAdvice> {
  let response: Response;
  try {
    response = await fetch("/api/v1/intelligence/incidents/advice", {
      method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ incident: { ...incident, title: incident.title.trim() || "Incident report" } }),
    });
  } catch { throw new Error("Could not reach emergency guidance. Your incident is unchanged."); }
  if (!response.ok) throw new Error(response.status === 422 ? "Check the report and incident fields before requesting guidance." : "Emergency guidance is unavailable. Your incident is unchanged.");
  try { return await response.json() as EmergencyAdvice; }
  catch { throw new Error("Emergency guidance returned an unreadable response."); }
}

export function EmergencyAdviceResult({ data }: { data: EmergencyAdvice }) {
  return <div className="space-y-4">
    <p role="status" className="text-sm">{data.advice_status === "completed" ? data.proposal?.summary : data.advice_status === "unavailable" ? "Emergency guidance is unavailable. Configure the server API key or continue manually." : data.advice_status === "refused" ? "The model declined this request. Continue manually." : "The guidance request failed. Try again or continue manually."}</p>
    {data.proposal && <><ol className="space-y-3">{data.proposal.actions.map((action, i) => <li key={i} className="rounded-lg border border-slate-200 p-4">
      <p className="text-xs font-semibold uppercase text-teal-700">{action.priority === "immediate" ? "First steps" : "Follow-up"} · {action.facility_ids.join(", ") || "Network coordination"}</p>
      <h3 className="mt-1 font-semibold">{i + 1}. {action.title}</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{action.steps.map((step, j) => <li key={j}>{step}</li>)}</ul>
      <p className="mt-3 text-sm text-slate-600">Why: {action.rationale}</p>
      <p className="mt-3 text-xs font-semibold">Verify before acting</p><ul className="mt-1 list-disc space-y-1 pl-5 text-xs">{action.prerequisites.map((item, j) => <li key={j}>{item}</li>)}</ul>
      <details className="mt-3 text-xs"><summary className="cursor-pointer font-medium">Supporting report and hospital data</summary><ul className="mt-2 space-y-2">{action.evidence_paths.map((path) => <li key={path}><span className="break-all font-medium">{path}</span>: {String(data.evidence.find((item) => item.path === path)?.value ?? "Unknown (null)")}</li>)}</ul></details>
    </li>)}</ol>{data.proposal.questions.length > 0 && <div><h3 className="text-sm font-semibold">Information needed</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{data.proposal.questions.map((question, i) => <li key={i}>{question}</li>)}</ul></div>}</>}
    <ul className="space-y-1 text-xs text-amber-900">{data.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>
    <p className="text-xs text-slate-500">Model: {data.model ?? "Not supplied"} · {data.elapsed_ms} ms · Hospital data as of <Timestamp value={data.as_of} /></p>
  </div>;
}

export function EmergencyAdvicePanel({ incident, disabled }: { incident: IncidentFields; disabled: boolean }) {
  const [state, setState] = useState<ComponentState<EmergencyAdvice>>({ phase: "idle" });
  const generation = useRef(0);
  const input = JSON.stringify(incident);
  useEffect(() => { ++generation.current; setState({ phase: "idle" }); return () => { ++generation.current; }; }, [input]);
  async function request() {
    const current = ++generation.current;
    setState({ phase: "loading" });
    try {
      const data = await requestEmergencyAdvice(incident);
      if (current === generation.current) setState({ phase: "ready", data });
    } catch (error) {
      if (current === generation.current) setState({ phase: "error", message: error instanceof Error ? error.message : "Guidance failed." });
    }
  }
  return <section className={`${panelClass} space-y-4 p-5`}>
    <h2 className="text-lg font-semibold">Emergency next steps</h2>
    <p className="text-sm text-slate-600">Get prioritized suggestions using this incident and current hospital reports. Suggested resource moves need confirmation; no action runs automatically.</p>
    <button className={secondaryClass} disabled={disabled || !incident.report_text?.trim() || state.phase === "loading"} onClick={() => void request()}>{state.phase === "loading" ? "Preparing next steps…" : "Suggest emergency next steps · live"}</button>
    {state.phase === "idle" && <p className="text-xs text-slate-500">Add a report or load the fictional Hospital B outage to begin. Changing incident details clears previous guidance.</p>}
    {state.phase === "loading" && <p role="status" className="text-sm">Reviewing the report, hospital service status, resources and modeled capacity…</p>}
    {state.phase === "error" && <p role="alert" className="text-sm text-rose-800">{state.message}</p>}
    {state.phase === "ready" && <EmergencyAdviceResult data={state.data} />}
  </section>;
}
