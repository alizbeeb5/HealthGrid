"use client";
import { useExercise } from "../exercise/context";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { buttonClass, panelClass, secondaryClass, Timestamp } from "../facilities/shared";
import { money } from "../allocation/model";
import { blankDetails, decisionStatuses, type Decision, type DecisionDetails, type DecisionSource, type OutcomeReview } from "./model";
import { exampleSources, loadDecisionSource, listDecisionRecords, getDecisionRecord, presentDecision, createDecision, decisionEventRequest, postDecisionEvent, captureReview, getReview, listReviews, type DecisionWire } from "./source";
import { FacilityClientError } from "../../lib/api/facilities";
import { decisionPreviewStore, type PreviewStore } from "./preview-client";
import { DecisionDetail, DetailsFields, inputClass } from "./decision-detail";
import { OutcomePanel } from "./outcome-panel";

export function DecisionDashboard() {
  const exercise = useExercise();
  const params = useSearchParams(); const mode = !exercise?.enabled && params.get("mode") === "example" ? "example" : "api";
  const decisionId = params.get("decision_id"); const reviewId = params.get("review_id");
  const sourceRunId = params.get("source_run_id"); const sourceType = params.get("source_type");
  const [records, setRecords] = useState<{ decisions: Decision[]; reviews: OutcomeReview[] }>({ decisions: [], reviews: [] });
  const [source, setSource] = useState<DecisionSource>(); const [details, setDetails] = useState<DecisionDetails>(blankDetails);
  const [exampleKind, setExampleKind] = useState<"allocation" | "investment">("allocation");
  const [actor, setActor] = useState(""); const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true); const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>(); const [notice, setNotice] = useState<string>();
  const [attempt, setAttempt] = useState(0); const [status, setStatus] = useState("all"); const [search, setSearch] = useState(""); const [blockedOnly, setBlockedOnly] = useState(false);
  const [manualType, setManualType] = useState<"allocation" | "investment">("allocation"); const [manualId, setManualId] = useState("");
  const [sample, setSample] = useState<"insufficient" | "supported" | "below" | "early">("insufficient");
  const client = useRef<PreviewStore | null>(null); const lock = useRef(false);
  const wireRecords = useRef<DecisionWire[]>([]); const generation = useRef(0);
  const [windowStart, setWindowStart] = useState("");
  const [existingId, setExistingId] = useState<string>();
  function errorText(cause: unknown): string {
    if (cause instanceof FacilityClientError && cause.detail) {
      const detail = cause.detail as unknown as { fields: { field: string; message: string }[]; current_version?: number | null; existing_decision_id?: string | null };
      setExistingId(detail.existing_decision_id ?? undefined);
      return [cause.message, ...detail.fields.map((f) => `${f.field}: ${f.message}`), ...(detail.current_version ? [`Current version: ${detail.current_version}. Refresh before recording another event.`] : [])].join("\n");
    }
    return cause instanceof Error ? cause.message : "Could not complete the decision request.";
  }
  function acceptRecord(record: DecisionWire) {
    wireRecords.current = [record, ...wireRecords.current.filter((r) => r.decision_id !== record.decision_id)];
    setRecords((previous) => ({ ...previous, decisions: wireRecords.current.map((r) => presentDecision(r, wireRecords.current)) }));
  }
  useEffect(() => {
    let active = true; ++generation.current; setLoading(true); setError(undefined); setSource(undefined); setRecords({ decisions: [], reviews: [] });
    void (async () => {
      try {
        if (mode === "example") {
          const store = decisionPreviewStore(window.localStorage); client.current = store; const data = store.list();
          if (decisionId && !data.decisions.some((item) => item.decision_id === decisionId)) throw new Error("Saved local decision not found.");
          if (reviewId && !data.reviews.some((item) => item.review_id === reviewId && item.decision_id === decisionId)) throw new Error("This saved evidence review does not match the selected decision.");
          if (active) { setRecords(data); setSource(exampleSources().find((item) => item.source_type === exampleKind)); }
        } else {
          client.current = null;
          const listed = await listDecisionRecords();
          let all = listed.items;
          if (decisionId) {
            const selected = await getDecisionRecord(decisionId);
            if (selected.decision_id !== decisionId) throw new Error("Decision response does not match the selected record.");
            all = [selected, ...all.filter((r) => r.decision_id !== decisionId)];
          } else if (reviewId) throw new Error("Select a decision to reopen its review.");
          const history = decisionId ? await listReviews(decisionId) : [];
          const savedReview = decisionId && reviewId ? await getReview(decisionId, reviewId) : undefined;
          if (savedReview && !history.some((r) => r.review_id === savedReview.review_id)) history.push(savedReview);
          if (active) {
            wireRecords.current = all;
            setRecords({ decisions: all.map((r) => presentDecision(r, all)), reviews: history });
            const selected = all.find((r) => r.decision_id === decisionId);
            if (selected) setWindowStart(savedReview?.window_starts_at ?? selected.expectation.baseline_captured_at);
          }
          if (sourceRunId) {
            if (sourceType !== "allocation" && sourceType !== "investment") throw new Error("Select allocation or investment as the source type.");
            const selected = await loadDecisionSource(sourceType, sourceRunId); if (active) setSource(selected);
          }
        }
      } catch (cause) { if (active) setError(errorText(cause)); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; ++generation.current; };
  }, [mode, sourceRunId, sourceType, decisionId, reviewId, exampleKind, attempt]);
  const decision = records.decisions.find((item) => item.decision_id === decisionId);
  const reviews = records.reviews.filter((item) => item.decision_id === decision?.decision_id);
  const selectedReview = reviewId ? reviews.find((item) => item.review_id === reviewId) : reviews[0];
  function open(id?: string, review?: string) {
    const query = new URLSearchParams(mode === "example" ? { mode: "example" } : {}); if (id) query.set("decision_id", id); if (review) query.set("review_id", review);
    window.history.replaceState(null, "", `/decisions?${query}`);
  }
  function operate(work: (store: PreviewStore) => void) {
    if (lock.current) return; lock.current = true; setPending(true); setError(undefined); setNotice(undefined);
    try { if (!client.current || mode !== "example") throw new Error("Browser preview operations require explicit example mode."); work(client.current); setRecords(client.current.list()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save the local decision preview."); }
    finally { lock.current = false; setPending(false); }
  }
  async function operateApi(work: (current: number) => Promise<void>) {
    if (lock.current) return; lock.current = true; setPending(true); setError(undefined); setExistingId(undefined); setNotice(undefined);
    const current = generation.current;
    try { await work(current); }
    catch (cause) { if (current === generation.current) setError(errorText(cause)); }
    finally { lock.current = false; setPending(false); }
  }
  function create() {
    if (!source) return;
    if (mode === "example") { operate((store) => { const record = store.create(source, details, actor); open(record.decision_id); setDetails(blankDetails()); setNotice("Local preview draft saved; reopen this URL to retain its timeline."); }); return; }
    void operateApi(async (current) => {
      const record = await createDecision(source, details, actor);
      if (current !== generation.current) return;
      acceptRecord(record); open(record.decision_id); setDetails(blankDetails()); setNotice("Decision draft saved by the API.");
    });
  }
  function send(command: Parameters<PreviewStore["event"]>[4]) {
    if (!decision) return;
    if (mode === "example") { operate((store) => { store.event(decision.decision_id, decision.version, actor, note, command); setNotice("Local event appended. Approval/progress did not update hospital inventory."); }); return; }
    void operateApi(async (current) => {
      const request = decisionEventRequest(decision.version, actor, note, command, crypto.randomUUID(), exercise?.clock ?? undefined);
      const record = await postDecisionEvent(decision.decision_id, request);
      if (current !== generation.current) return;
      acceptRecord(record); setNotice("Event saved. Approval and progress reports do not change hospital inventory.");
    });
  }
  function capture() {
    if (!decision) return;
    if (mode === "example") { operate((store) => { const result = store.review(decision.decision_id, sample, actor, note); open(decision.decision_id, result.review_id); setNotice("Fixed synthetic review saved. No live observations were captured or capacity calculations run."); }); return; }
    void operateApi(async (current) => {
      const result = await captureReview(decision.decision_id, actor, note, windowStart, crypto.randomUUID());
      if (current !== generation.current) return;
      setRecords((previous) => ({ ...previous, reviews: [result, ...previous.reviews] }));
      open(decision.decision_id, result.review_id); setNotice("Current reports captured, evaluated and saved. This review URL reopens its original evidence.");
    });
  }
  const visible = records.decisions.filter((item) => (status === "all" || item.status === status) && `${item.title} ${item.owner_name}`.toLowerCase().includes(search.toLowerCase()) && (!blockedOnly || item.actions.some((action) => action.status === "blocked")));
  const prerequisites = records.decisions.filter((item) => item.source.source_type === "allocation" && item.source.source_run_id === source?.allocation_run_id && !["rejected", "cancelled"].includes(item.status));
  return <div className="space-y-6"><header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-wider text-teal-700">Ministry / Follow-up review</p><h1 className="mt-2 text-3xl font-bold">Decisions and outcome evidence</h1><p className="mt-3 text-sm text-slate-600">Choose → review → report progress → update reports → review evidence.</p></div><Link className={secondaryClass} href="/allocation">Saved proposals</Link></header>
    <div role="note" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><strong>{mode === "example" ? "Frontend preview · synthetic local records" : "Connected decisions and outcome reviews"}</strong><p className="mt-2">{mode === "example" ? "Local workflow and frozen evidence samples only. No decision API or outcome engine runs; no reports are changed." : "Decisions and events are saved by the API. Follow-up reviews freeze current hospital reports and compare them with the saved proposal."} Actor and owner names are self-reported demo identities; no authenticated roles, verified signatures, notifications, dispatch or purchasing are provided.</p>{!exercise?.enabled && <Link className="mt-3 inline-block font-semibold underline" href={mode === "example" ? "/decisions" : "/decisions?mode=example"}>{mode === "example" ? "Open saved-proposal view" : "Open explicit browser workflow example"}</Link>}</div>
    {loading && <p role="status" className={`${panelClass} p-6`}>Loading decision workspace…</p>}{error && <div role="alert" className="whitespace-pre-line rounded border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}{existingId && <button className={`${secondaryClass} ml-3`} onClick={() => open(existingId)}>Open existing decision</button>}<button className={`${secondaryClass} ml-3`} onClick={() => setAttempt((value) => value + 1)}>Refresh workspace</button></div>}{notice && <p role="status" className="rounded bg-teal-50 p-4 text-sm text-teal-950">{notice}</p>}
    {!loading && <>
      <section className={`${panelClass} grid gap-4 p-5 sm:grid-cols-2`}><label className="text-sm font-medium">Acting / reviewing as (demo name)<input className={inputClass} value={actor} onChange={(event) => setActor(event.target.value)} /></label><label className="text-sm font-medium">Event / review explanation<textarea className={inputClass} rows={2} value={note} onChange={(event) => setNote(event.target.value)} /><span className="mt-1 block text-xs font-normal text-slate-500">Required for approval, rejection, cancellation, completion and corrections.</span></label></section>
      {!decision && <section className={`${panelClass} space-y-4 p-5`}><h2 className="text-lg font-semibold">Record a decision from a saved proposal</h2>{mode === "example" ? <label className="block text-sm">Synthetic proposal<select className={inputClass} value={exampleKind} onChange={(event) => { setExampleKind(event.target.value as typeof exampleKind); setDetails(blankDetails()); }}><option value="allocation">Transfer one monitor A → B</option><option value="investment">Repair + commission B monitors (requires transfer decision)</option></select></label> : <div className="grid gap-3 sm:grid-cols-3"><label className="text-xs">Source type<select className={inputClass} value={manualType} onChange={(event) => setManualType(event.target.value as typeof manualType)}><option value="allocation">Allocation</option><option value="investment">Investment</option></select></label><label className="text-xs">Saved proposal ID<input className={inputClass} value={manualId} onChange={(event) => setManualId(event.target.value)} /></label><button className={`${secondaryClass} self-end`} disabled={!manualId.trim()} onClick={() => window.history.replaceState(null, "", `/decisions?${new URLSearchParams({ source_type: manualType, source_run_id: manualId.trim() })}`)}>Inspect saved source</button></div>}
      {source && <><p className="break-all text-xs text-slate-600">{source.source_type}: {source.source_run_id} · Frozen proposed cost {money(source.total_cost_minor_units)} · Expected date {source.expected_at ?? "Frozen by the decision service on saving"}</p><ul className="space-y-1 text-xs text-slate-600">{source.evidence.map((item) => <li key={item}>{item}</li>)}</ul><DetailsFields value={details} change={setDetails} disabled={pending} />{source.has_transfer_prerequisite && <label className="block text-sm font-medium">Exact source allocation prerequisite decision<select className={inputClass} value={details.prerequisite_decision_id ?? ""} onChange={(event) => setDetails({ ...details, prerequisite_decision_id: event.target.value || null })}><option value="">Record/select the transfer decision first</option>{prerequisites.map((item) => <option key={item.decision_id} value={item.decision_id}>{item.title} · {item.status}</option>)}</select></label>}{<label className="block text-xs">Supersedes terminal decision (optional)<select className={inputClass} value={details.supersedes_decision_id ?? ""} onChange={(event) => setDetails({ ...details, supersedes_decision_id: event.target.value || null })}><option value="">None</option>{records.decisions.filter((item) => ["rejected", "cancelled", "completed"].includes(item.status)).map((item) => <option key={item.decision_id} value={item.decision_id}>{item.title} · {item.status}</option>)}</select></label>}<button className={buttonClass} disabled={pending} onClick={create}>{mode === "example" ? "Save local decision draft" : "Save decision draft"}</button></>}
      </section>}
      {<section className={`${panelClass} space-y-4 p-5`}><div className="flex flex-wrap justify-between gap-3"><h2 className="text-lg font-semibold">{mode === "example" ? "Local decision board" : "Saved decision board"}</h2><button className={secondaryClass} disabled={pending} onClick={() => open()}>New decision</button></div><div className="grid gap-3 sm:grid-cols-3"><label className="text-xs">Status<select className={inputClass} value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">All states</option>{decisionStatuses.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select></label><label className="text-xs">Title or owner<input className={inputClass} value={search} onChange={(event) => setSearch(event.target.value)} /></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={blockedOnly} onChange={(event) => setBlockedOnly(event.target.checked)} />Only blocked work</label></div>{!visible.length && <p className="text-sm text-slate-500">No decisions match this view. Start with the transfer decision before creating the investment decision.</p>}<ul className="divide-y divide-slate-100">{visible.map((item) => <li key={item.decision_id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div><p className="text-sm font-semibold">{item.title} · {item.status.replaceAll("_", " ")}</p><p className="mt-1 text-xs text-slate-500">Owner {item.owner_name} · Target <Timestamp value={item.target_completion_at} /></p>{!["completed", "cancelled", "rejected"].includes(item.status) && Date.parse(item.target_completion_at) < (exercise?.clock ? Date.parse(exercise.clock) : Date.now()) && <p className="mt-1 text-xs text-amber-900">Past target date (not evidence of execution failure)</p>}{item.actions.some((action) => action.status === "blocked") && <p className="mt-1 text-xs text-amber-900">Blocked action reported</p>}</div><button className={secondaryClass} disabled={pending} onClick={() => open(item.decision_id)}>Open decision</button></li>)}</ul></section>}
      {decision && <><DecisionDetail key={`${decision.decision_id}:${decision.version}`} decision={decision} all={records.decisions} reviews={reviews} send={send} disabled={pending} open={(id) => open(id)} /><section className={`${panelClass} space-y-4 p-5`}><h2 className="text-lg font-semibold">Separate outcome evidence review</h2><p className="text-xs text-slate-600">{mode === "example" ? "This preview uses fixed evidence samples; it does not capture live report updates." : "Update hospital reports through the links above, then capture current evidence. The server supplies capture time; saved reviews retain the decision version and original reports."}</p>{mode === "example" ? <label className="block text-sm">Synthetic evidence state<select className={inputClass} value={sample} onChange={(event) => setSample(event.target.value as typeof sample)}><option value="insufficient">Missing fresh required evidence</option><option value="supported">Fresh fixture matches expected capacity</option><option value="below">Fresh fixture below expected capacity</option><option value="early">Review before expected date</option></select></label> : <label className="block text-sm">Observation window starts at (UTC)<input className={inputClass} disabled={pending} type="datetime-local" value={windowStart.slice(0, 16)} onChange={(event) => setWindowStart(event.target.value ? `${event.target.value}:00Z` : "")} /><span className="mt-1 block text-xs text-slate-500">Choose the follow-up period explicitly. Reports outside this window cannot support the outcome.</span></label>}<button className={secondaryClass} disabled={pending || (mode === "api" && !["approved", "in_progress", "completed"].includes(decision.status))} onClick={capture}>{mode === "example" ? "Save fixed evidence review example" : "Capture and save current evidence"}</button><ul className="space-y-2">{reviews.map((item) => <li key={item.review_id}><button className="text-sm font-semibold text-teal-800 underline" onClick={() => open(decision.decision_id, item.review_id)}>Reopen review · <Timestamp value={item.captured_at} /> · version {item.decision_version}</button></li>)}</ul></section>{selectedReview && <OutcomePanel review={selectedReview} />}</>}
    </>}
  </div>;
}
