"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { buttonClass, panelClass, secondaryClass, Timestamp } from "../facilities/shared";
import { snapshots as exampleSnapshots, blankIncident, outageExample, outageReport, validateIncident, type Assessment, type Extraction, type IncidentFields, type PreviewRevision, type PreviewRun } from "./model";
import { createPreviewClient, extractionSample, type IncidentClient } from "./preview-client";
import { createIncidentApiClient, loadIncidentCatalog, IncidentRequestError } from "./api-client";
import type { FacilitySnapshotResponse } from "../../lib/api/feature-1";
import { IncidentForm, inputClass } from "./incident-form";
import { AIReview, AssumptionReview, type ComponentState } from "./review-panel";
import { ImpactComparison } from "./impact-comparison";
import { EmergencyAdvicePanel } from "./emergency-advice";

export function IncidentDashboard() {
  const params = useSearchParams();
  const mode = params.get("mode") === "example" ? "example" : "api";
  const [snapshots, setSnapshots] = useState<FacilitySnapshotResponse[]>([]);
  const [uncertain, setUncertain] = useState(false);
  const [conflictRevision, setConflictRevision] = useState<string>();
  const [loadedMode, setLoadedMode] = useState<string>();
  const [loadAttempt, setLoadAttempt] = useState(0);
  const nextInput = useRef<IncidentFields | null>(null);
  const requestedIncident = params.get("incident_id");
  const client = useRef<IncidentClient | null>(null);
  const [fields, setFields] = useState<IncidentFields>(blankIncident);
  const [revision, setRevision] = useState<PreviewRevision>();
  const [run, setRun] = useState<PreviewRun>();
  const [records, setRecords] = useState<{ revisions: PreviewRevision[]; runs: PreviewRun[] }>({ revisions: [], runs: [] });
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [step, setStep] = useState<"edit" | "review" | "confirmed">("edit");
  const [reviewer, setReviewer] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [assessment, setAssessment] = useState<ComponentState<Assessment>>({ phase: "idle" });
  const [extraction, setExtraction] = useState<ComponentState<Extraction>>({ phase: "idle" });
  const [proposalVersion, setProposalVersion] = useState(-1);
  const editVersion = useRef(0);
  const reportGeneration = useRef(0);
  const assessGeneration = useRef(0);
  const extractGeneration = useRef(0);
  const actionLock = useRef(false);
  const [viewVersion, setViewVersion] = useState(0);
  const requestedRevision = params.get("revision_id");
  const requestedRun = params.get("run_id");

  useEffect(() => {
    let active = true;
    setLoading(true); setLoadedMode(undefined); setError(undefined); setRun(undefined); setRevision(undefined); setFields(blankIncident()); setStep("edit");
    void (async () => {
      try {
        const source = mode === "example" ? createPreviewClient(window.localStorage) : createIncidentApiClient(); client.current = source;
        const [list, catalog] = await Promise.all([source.list(), mode === "example" ? Promise.resolve(exampleSnapshots) : loadIncidentCatalog()]);
        const nextRun = requestedRun ? await source.getRun(requestedRun) : undefined;
        const nextRevision = requestedRevision ? await source.getRevision(requestedRevision, requestedIncident ?? undefined) : nextRun ? await source.getRevision(nextRun.revision_id, nextRun.incident_id) : undefined;
        if (!active) return;
        if (nextRun && nextRevision && nextRun.revision_id !== nextRevision.revision_id) throw new Error("The requested revision does not match this saved run. Open the run URL without a different revision ID.");
        setSnapshots(catalog); setRecords({ ...list, runs: nextRun ? [nextRun, ...list.runs.filter((item) => item.run_id !== nextRun.run_id)] : list.runs }); setRun(nextRun); setRevision(nextRevision); setLoadedMode(mode); setUncertain(false); setConflictRevision(undefined);
        setFields(nextRevision ? structuredClone(nextRevision.input) : nextInput.current ?? blankIncident()); nextInput.current = null;
        setStep(nextRevision?.status === "confirmed" ? "confirmed" : "edit");
        setAssessment({ phase: "idle" }); setExtraction({ phase: "idle" });
        ++editVersion.current; ++reportGeneration.current; ++assessGeneration.current; ++extractGeneration.current;
        setViewVersion(editVersion.current); setAccepted(false);
      } catch (cause) { if (active) setError(cause instanceof Error ? cause.message : "Incident workspace could not be loaded."); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; ++reportGeneration.current; ++assessGeneration.current; ++extractGeneration.current; };
  }, [requestedRevision, requestedRun, requestedIncident, mode, loadAttempt]);

  function change<K extends keyof IncidentFields>(key: K, value: IncidentFields[K]) {
    ++editVersion.current; setViewVersion(editVersion.current);
    setFields((previous) => ({ ...previous, [key]: value })); setAccepted(false); setError(undefined); setNotice(undefined);
    if (key === "report_text") { ++reportGeneration.current; ++assessGeneration.current; ++extractGeneration.current; setAssessment({ phase: "idle" }); setExtraction({ phase: "idle" }); }
  }
  function replaceFields(next: IncidentFields) {
    nextInput.current = requestedRevision || requestedRun ? structuredClone(next) : null;
    ++editVersion.current; ++reportGeneration.current; ++assessGeneration.current; ++extractGeneration.current;
    setViewVersion(editVersion.current); setFields(structuredClone(next)); setRevision(undefined); setRun(undefined); setStep("edit"); setAccepted(false);
    setAssessment({ phase: "idle" }); setExtraction({ phase: "idle" }); setError(undefined); setNotice(undefined);
  }
  function navigate(key?: "revision_id" | "run_id", id?: string, incidentId?: string) {
    const queryParams = new URLSearchParams();
    if (mode === "example") queryParams.set("mode", "example");
    if (key && id) queryParams.set(key, id);
    if (incidentId) queryParams.set("incident_id", incidentId);
    const query = queryParams.size ? `?${queryParams}` : "";
    window.history.replaceState(null, "", `/scenarios${query}`);
  }
  async function action(work: (source: IncidentClient) => Promise<void>, writing = true) {
    if (actionLock.current || (writing && uncertain)) return;
    actionLock.current = true; setPending(true); setError(undefined); setNotice(undefined);
    try { if (!client.current) throw new Error("Incident source is not ready. Reload the page."); await work(client.current); setRecords(await client.current.list()); if (!writing) { setUncertain(false); setConflictRevision(undefined); } }
    catch (cause) {
      if (cause instanceof IncidentRequestError) { if (cause.uncertain) setUncertain(true); setConflictRevision(cause.existingRevisionId); setError([cause.message, ...cause.fields.map((field) => `${field.field}: ${field.message}`)].join(" ")); }
      else setError(cause instanceof Error ? cause.message : "Could not save. Reopen saved items before trying again.");
    }
    finally { actionLock.current = false; setPending(false); }
  }
  async function save() {
    const errors = validateIncident(fields, false, snapshots);
    if (errors.length) { setError(errors.join(" ")); return; }
    await action(async (source) => { const saved = await source.saveDraft(fields); setRevision(saved); navigate("revision_id", saved.revision_id, saved.incident_id); setNotice("Draft saved. Reopen it below or reload this URL."); });
  }
  function review() {
    const errors = validateIncident(fields, true, snapshots);
    if (errors.length) { setError(errors.join(" ")); return; }
    setError(undefined); setAccepted(false); setStep("review");
  }
  async function confirm() {
    if (!accepted || !reviewer.trim()) { setError("Review the visible assumptions, enter a demo display name and check the confirmation box."); return; }
    await action(async (source) => {
      const reviewed = structuredClone(fields);
      // A fresh draft retains the exact visible report and assumptions before confirmation.
      const draft = revision?.status === "draft" && JSON.stringify(revision.input) === JSON.stringify(reviewed) ? revision : await source.saveDraft(reviewed);
      setRevision(draft);
      const confirmed = await source.confirm(draft.revision_id, reviewed, reviewer);
      setRevision(confirmed); setStep("confirmed"); navigate("revision_id", confirmed.revision_id, confirmed.incident_id);
      setNotice("Assumptions confirmed. The baseline is immutable; subsequent reports do not change this revision.");
    });
  }
  async function simulate() {
    if (!revision) return;
    await action(async (source) => { const result = await source.simulate(revision.revision_id); setRun(result); navigate("run_id", result.run_id); setNotice("Comparison saved. Reload this URL to reopen its frozen baseline and result."); });
  }
  async function assess() {
    const report = fields.report_text; if (!report?.trim() || !client.current) return;
    const generation = ++assessGeneration.current; const reportVersion = reportGeneration.current;
    setAssessment({ phase: "loading" });
    try { const data = await client.current.assess(report); if (generation === assessGeneration.current && reportVersion === reportGeneration.current) setAssessment({ phase: "ready", data }); }
    catch (cause) { if (generation === assessGeneration.current && reportVersion === reportGeneration.current) setAssessment({ phase: "error", message: cause instanceof Error ? cause.message : "Assessment failed; manual input is retained." }); }
  }
  async function extract() {
    const report = fields.report_text; if (!report?.trim() || !client.current) return;
    const generation = ++extractGeneration.current; const reportVersion = reportGeneration.current; const version = editVersion.current;
    setExtraction({ phase: "loading" });
    try {
      const data = await client.current.extract(report);
      if (generation !== extractGeneration.current || reportVersion !== reportGeneration.current) return;
      if (data.evidence.some((item) => !report.includes(item.source_excerpt))) throw new Error("Proposal evidence does not match this report. No fields changed.");
      setExtraction({ phase: "ready", data }); setProposalVersion(version);
    } catch (cause) { if (generation === extractGeneration.current && reportVersion === reportGeneration.current) setExtraction({ phase: "error", message: cause instanceof Error ? cause.message : "Extraction failed; manual input is retained." }); }
  }
  function sample() {
    ++extractGeneration.current; ++assessGeneration.current;
    try {
      const data = extractionSample(fields.report_text ?? ""); setExtraction({ phase: "ready", data }); setProposalVersion(editVersion.current);
      setAssessment({ phase: "ready", data: { status: "completed", answers: [
        { question: "outage_reported", value: "yes", answer_status: "answered" },
        { question: "multiple_facilities_reported", value: "no", answer_status: "answered" },
        { question: "resource_loss_reported", value: "unclear", answer_status: "answered" },
        { question: "clarification_needed", value: "yes", answer_status: "answered" },
      ], model: null, elapsed_ms: null, rubric_version: "emergency-review-v1", message: "Synthetic display example; no OpenAI call was made." } });
    } catch (cause) { setExtraction({ phase: "error", message: cause instanceof Error ? cause.message : "Example unavailable." }); }
  }
  const canAccept = extraction.phase === "ready" && !!extraction.data.candidate && proposalVersion === viewVersion;
  function accept() {
    if (!canAccept || extraction.phase !== "ready" || !extraction.data.candidate) return;
    const candidate = { ...structuredClone(extraction.data.candidate), report_text: fields.report_text };
    const errors = validateIncident(candidate, false, snapshots);
    if (errors.length) { setError(errors.join(" ")); return; }
    change("title", candidate.title); change("service_id", candidate.service_id); change("starts_at", candidate.starts_at); change("expected_ends_at", candidate.expected_ends_at); change("affected_facility_ids", candidate.affected_facility_ids); change("service_overrides", candidate.service_overrides); change("resource_overrides", candidate.resource_overrides); change("assumptions", candidate.assumptions);
    setNotice("Reviewed proposal copied to the form. Inspect and edit it before confirming.");
  }

  return <div className="space-y-6"><header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-wider text-teal-700">Ministry / Emergency planning</p><h1 className="mt-2 text-3xl font-bold">Incident assessment and impact</h1><p className="mt-3 text-sm text-slate-600">Declare → review → confirm assumptions → compare → reopen.</p></div><Link href="/overview" className={secondaryClass}>Network overview</Link></header>
    <div role="note" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><strong className="flex items-center gap-2"><AlertTriangle size={17} aria-hidden="true" />{mode === "example" ? "Frontend preview · synthetic data · browser storage only" : "Connected incident API · human-reviewed assumptions"}</strong><p className="mt-2">{mode === "example" ? "The B outage comparison is a fixed browser display fixture. No engine or OpenAI call runs in this example mode." : "Drafts, confirmed baselines and Python-engine comparisons are saved by the API. Assess report sends a live OpenAI Decisions request through the server. Extract fields uses a separate Responses request. Manual entry works without an OpenAI key."} Use synthetic reports for the demo. Quantities represent modeled simultaneous service places, not confirmed spare admission capacity.</p></div>
    <Link className="inline-block text-sm font-semibold text-teal-800 underline" href={mode === "example" ? "/scenarios" : "/scenarios?mode=example"}>{mode === "example" ? "Open connected incident API" : "Open isolated browser example"}</Link>
    {loading && <section className={`${panelClass} p-6`} role="status">Loading saved incidents…</section>}
    {error && <div role="alert" tabIndex={-1} className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}</div>}
    {notice && <div role="status" className="rounded-lg border border-teal-200 bg-teal-50 p-4 text-sm text-teal-950">{notice}</div>}
    {!loading && loadedMode !== mode && <button className={secondaryClass} onClick={() => setLoadAttempt((value) => value + 1)}>Retry loading incidents</button>}
    {conflictRevision && revision && <button className={secondaryClass} disabled={pending} onClick={() => navigate("revision_id", conflictRevision, revision.incident_id)}>Open existing confirmed revision</button>}
    {uncertain && <p role="alert" className="text-sm text-amber-900">Further saves are blocked because the last save could not be confirmed. Refresh saved incidents and reopen the latest revision before trying again.</p>}
    {!loading && loadedMode === mode && <>
      <div className="flex flex-wrap gap-2"><button className={secondaryClass} disabled={pending} onClick={() => { replaceFields(blankIncident()); navigate(); }}>New incident</button><button className={secondaryClass} disabled={pending || step !== "edit"} onClick={() => { replaceFields(outageExample()); navigate(); }}>Load synthetic B outage</button><button className={secondaryClass} disabled={pending || step !== "edit"} onClick={() => { replaceFields({ ...blankIncident(), title: "Outage report draft", report_text: outageReport }); navigate(); }}>Load sample report for AI review</button><button className={secondaryClass} disabled={pending} onClick={() => void action(async () => { setNotice("Saved incidents refreshed. Reopen the latest revision to inspect it."); }, false)}><RefreshCw size={15} aria-hidden="true" />Refresh saved items</button></div>
      {step === "edit" && <><IncidentForm snapshots={snapshots} value={fields} change={change} disabled={pending || uncertain} /><AIReview assessment={assessment} extraction={extraction} assess={() => void assess()} extract={() => void extract()} sample={sample} accept={accept} canAccept={canAccept} hasReport={!!fields.report_text?.trim()} pending={pending || uncertain} allowSample={mode === "example"} />{mode === "api" && <EmergencyAdvicePanel incident={fields} disabled={pending || uncertain} />}<div className="flex flex-wrap gap-3"><button className={secondaryClass} disabled={pending || uncertain} onClick={() => void save()}>{mode === "example" ? "Save local draft" : "Save draft"}</button><button className={buttonClass} disabled={pending || uncertain} onClick={review}>Review assumptions</button></div></>}
      {step === "review" && <section className={`${panelClass} space-y-5 p-5`}><h2 className="text-lg font-semibold">Review and confirm assumptions</h2><AssumptionReview input={fields} /><p className="text-xs text-slate-600">{mode === "example" ? "The frozen example baseline is October 10, 2026 at 09:00 UTC: A unknown, B 5 places, C unavailable with 0." : "The backend captures current reports and full requirement profiles when you confirm. Missing, stale or limited reports remain visible in the saved comparison; the baseline is not a reconstruction of conditions at the incident start."}</p><details><summary className="cursor-pointer text-sm font-semibold text-teal-800">Inspect current catalog report limitations before confirmation</summary><ul className="mt-3 space-y-3 text-xs">{snapshots.filter((hospital) => hospital.services.some((service) => service.service_id === fields.service_id)).map((hospital) => <li key={hospital.facility.facility_id}><strong>{hospital.facility.name}</strong> · service {hospital.services.find((service) => service.service_id === fields.service_id)?.status} · snapshot <Timestamp value={hospital.as_of} /><ul className="mt-1 space-y-1">{hospital.resources.filter((resource) => resource.data_status !== "current").map((resource) => <li key={resource.resource_id}>{resource.name}: {resource.data_status} · observed <Timestamp value={resource.observed_at} /></li>)}</ul></li>)}</ul><p className="mt-3 text-xs text-slate-500">These are the catalog reports loaded for review. The server captures the authoritative baseline at confirmation; the saved comparison exposes its capacity profile and missing/stale evidence.</p></details><label className="block text-sm font-medium">Demo reviewer display name<input className={inputClass} maxLength={100} value={reviewer} onChange={(event) => setReviewer(event.target.value)} disabled={pending} /><span className="mt-1 block text-xs font-normal text-slate-500">Simulated role; not authenticated identity.</span></label><label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} disabled={pending} />I reviewed these visible assumptions and the baseline limitations. I understand this models one state and does not update reported observations.</label><div className="flex flex-wrap gap-3"><button className={secondaryClass} disabled={pending} onClick={() => { setStep("edit"); setAccepted(false); }}>Back to edit</button><button className={buttonClass} disabled={pending || uncertain || !accepted || !reviewer.trim()} onClick={() => void confirm()}>{pending ? "Saving…" : "Confirm assumptions"}</button></div></section>}
      {step === "confirmed" && revision && <section className={`${panelClass} space-y-4 p-5`}><h2 className="text-lg font-semibold">Confirmed incident</h2><p className="text-xs text-slate-600">Reviewer: {revision.confirmed_by} (demo display name) · <Timestamp value={revision.confirmed_at} /></p><AssumptionReview input={revision.input} /><button className={buttonClass} disabled={pending || uncertain} onClick={() => void simulate()}>{pending ? "Saving…" : run ? "Reopen saved comparison" : mode === "example" ? "Show and save fixed outage comparison" : "Simulate and save comparison"}</button><p className="text-xs text-slate-500">{mode === "example" ? "Only the B outage has a fixed display result in example mode." : "Python applies the reviewed service/resource assumptions to this revision’s frozen baseline. Repeating this action returns the same saved run for this engine version."}</p></section>}
      {run && <ImpactComparison run={run} example={mode === "example"} />}
      <section className={`${panelClass} p-5`}><h2 className="text-lg font-semibold">{mode === "example" ? "Saved in this browser" : "Saved incidents"}</h2><p className="mt-2 text-xs text-slate-500">Drafts and confirmations are separate immutable revisions. Editing a reopened draft saves a new incident. Confirmed inputs and results retain their original baseline.</p>{!records.revisions.length && <p className="mt-4 text-sm text-slate-600">No incidents saved yet. Create a manual draft or load the synthetic outage.</p>}<ul className="mt-4 divide-y divide-slate-100">{records.revisions.map((item) => <li key={item.revision_id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div><p className="text-sm font-medium">{item.input.title} · {item.status}</p><p className="mt-1 text-xs text-slate-500"><Timestamp value={item.created_at} /></p></div><button className={secondaryClass} disabled={pending} onClick={() => navigate("revision_id", item.revision_id, item.incident_id)}>Reopen {item.status}</button></li>)}</ul><h3 className="mt-5 text-sm font-semibold">Saved comparisons</h3>{!records.runs.length && <p className="mt-2 text-sm text-slate-500">{mode === "example" ? "No comparison saved yet." : "Open a confirmed incident and choose Simulate to create or retrieve its saved comparison. Saved run URLs reopen directly."}</p>}<ul className="mt-2 divide-y divide-slate-100">{records.runs.map((item) => <li key={item.run_id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div><p className="text-sm">{item.input.title}</p><p className="mt-1 text-xs text-slate-500"><Timestamp value={item.created_at} /></p></div><button className={secondaryClass} disabled={pending} onClick={() => navigate("run_id", item.run_id)}>Reopen comparison</button></li>)}</ul></section>
    </>}
  </div>;
}
