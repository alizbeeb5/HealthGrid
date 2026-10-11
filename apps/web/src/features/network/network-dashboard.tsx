"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, Map, RefreshCw, Search } from "lucide-react";
import { createNetworkClient, type NetworkMode, type NetworkService } from "../../lib/api/network";
import { facilityDataMode } from "../../lib/api/facilities";
import { buttonClass, LoadError, panelClass, secondaryClass, Timestamp } from "../facilities/shared";
import { AttentionList } from "./attention-list";
import { HospitalTable } from "./hospital-table";
import { createNetworkLoader, type NetworkState } from "./network-loader";
import { capacityFilter, capacityLabels, filterHospitals, initialService } from "./presentation";
import { summarizeNetwork, type NetworkSummary } from "./summary";
import { SummaryCards } from "./summary-cards";
import { PageHeader } from "../exercise/page-header";
import { ExerciseOverview } from "../exercise/overview";
import { useExercise } from "../exercise/context";

const HospitalMap = dynamic(() => import("./hospital-map"), {
  ssr: false,
  loading: () => <p role="status" className="p-8 text-sm text-slate-600">Loading hospital map… The comparison table is available below.</p>,
});
const inputClass = "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-teal-700 focus:outline-2 focus:outline-teal-100";

export function NetworkDashboard() {
  const exercise = useExercise();
  const params = useSearchParams();
  const [view, setView] = useState<"map" | "hospitals" | "plans">("map");
  const requested = params.get("service_id");
  const mode: NetworkMode = !exercise?.enabled && (facilityDataMode === "demo" || params.get("mode") === "example") ? "example" : "api";
  const name = params.get("name") ?? "";
  const status = capacityFilter(params.get("status"));
  const [state, setState] = useState<NetworkState>({ phase: "loading" });
  const [services, setServices] = useState<NetworkService[]>([]);
  const [attempt, setAttempt] = useState(0);
  const loader = useMemo(() => createNetworkLoader((next) => {
    setState(next);
    if ("services" in next) setServices(next.services);
  }), []);
  const refresh = useCallback(() => { loader.cancel(); setState({ phase: "updating" }); setAttempt((value) => value + 1); }, [loader]);

  useEffect(() => {
    void loader.refresh(createNetworkClient(mode), mode, requested);
    return () => loader.cancel();
  }, [loader, mode, requested, attempt]);
  useEffect(() => {
    const restored = (event: PageTransitionEvent) => { if (event.persisted) refresh(); };
    window.addEventListener("pageshow", restored);
    return () => window.removeEventListener("pageshow", restored);
  }, [refresh]);

  function updateQuery(changes: Record<string, string | null>, refetch = false) {
    if (refetch) { loader.cancel(); setState({ phase: "updating" }); }
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key); else next.set(key, value);
    }
    window.history.replaceState(null, "", `/overview${next.size ? `?${next}` : ""}`);
  }

  const selected = initialService(services, requested);
  const ready = state.phase === "ready" && state.mode === mode && (requested === null || requested === state.data.service_id) ? state : undefined;
  const pending = state.phase === "loading" || state.phase === "updating" || (state.phase === "ready" && !ready);
  const rows = ready ? filterHospitals(ready.data.facilities, name, status) : [];
  let summary: NetworkSummary | undefined;
  let summaryError: string | undefined;
  if (ready) {
    try { summary = summarizeNetwork(rows); }
    catch { summaryError = "The network results could not be summarized consistently. Refresh to load a new assessment."; }
  }
  const returnParams = new URLSearchParams(params.toString());
  if (ready) returnParams.set("service_id", ready.data.service_id);
  returnParams.set("mode", mode);
  const returnTo = `/overview?${returnParams}`;
  const unknownSelection = selected !== undefined && !services.some((service) => service.service_id === selected);
  const fictional = ready?.data.facilities.some((row) => row.capacity.profile_version?.startsWith("demo-"));

  return <div className="space-y-4">
    <PageHeader title={exercise?.enabled ? "Beirut hospital situation" : "Hospital situation"} actions={<><Link className={secondaryClass} href={exercise?.links?.scenarios ?? "/scenarios"}>Incident & AI</Link><button className={buttonClass} onClick={refresh} disabled={pending}><RefreshCw size={16} aria-hidden="true" />{pending ? "Refreshing…" : "Refresh"}</button></>} />
    <div className="flex flex-wrap items-center justify-between gap-3"><div role="group" aria-label="Dashboard view" className="inline-flex gap-1 rounded-lg border border-slate-200 bg-white p-1">{([['map', 'Map'], ['hospitals', 'Hospitals'], ...(exercise?.enabled ? [['plans', 'Plan comparison']] : [])] as [typeof view, string][]).map(([key, label]) => <button key={key} aria-pressed={view === key} onClick={() => setView(key)} className={`rounded-md px-4 py-2 text-sm font-medium ${view === key ? "bg-teal-50 text-teal-900" : "text-slate-500 hover:bg-slate-50"}`}>{label}</button>)}</div>{view !== "plans" && ready && <p className="text-xs text-slate-500">{summary?.calculated_count ?? 0} assessed · {summary?.unavailable_count ?? 0} interrupted · {summary?.unknown_count ?? 0} need reports</p>}</div>

    {view !== "plans" && <section className="rounded-xl border border-slate-200 bg-white p-3" aria-label="Dashboard filters">
      <div className={`grid gap-4 md:grid-cols-2 ${exercise?.enabled ? "" : "lg:grid-cols-4"}`}>
        {!exercise?.enabled && <label className="space-y-1 text-xs font-medium text-slate-600"><span className="block">Service</span><select className={`${inputClass} w-full`} value={selected ?? ""} onChange={(event) => updateQuery({ service_id: event.target.value }, true)} disabled={!services.length}>
          {!services.length && <option value="">{pending ? "Loading services…" : "No services available"}</option>}
          {unknownSelection && <option value={selected}>Service not listed ({selected})</option>}
          {services.map((service) => <option key={service.service_id} value={service.service_id}>{service.name}</option>)}
        </select></label>}
        <label className="space-y-1 text-xs font-medium text-slate-600"><span className="block">Hospital name</span><span className="relative block"><Search size={15} className="absolute left-3 top-2.5 text-slate-400" aria-hidden="true" /><input type="search" className={`${inputClass} w-full pl-9`} placeholder="Search hospital name" value={name} onChange={(event) => updateQuery({ name: event.target.value })} /></span></label>
        <label className="space-y-1 text-xs font-medium text-slate-600"><span className="block">Capacity status</span><select className={`${inputClass} w-full`} value={status} onChange={(event) => updateQuery({ status: event.target.value === "all" ? null : event.target.value })}><option value="all">All statuses</option>{Object.entries(capacityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {!exercise?.enabled && <label className="space-y-1 text-xs font-medium text-slate-600"><span className="block">Reports</span><select className={`${inputClass} w-full`} value={mode} onChange={(event) => updateQuery({ mode: event.target.value }, true)}><option value="api" disabled={facilityDataMode === "demo"}>Connected reports</option>{!exercise?.enabled && <option value="example">Shared demo examples (frozen)</option>}</select></label>}
      </div>
      {(name || status !== "all") && <button className="mt-3 text-xs font-semibold text-teal-800 hover:underline" onClick={() => updateQuery({ name: null, status: null })}>Clear name and status filters</button>}
    </section>}

    {mode === "example" && <div role="note" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><strong>Frozen synthetic preview</strong><p className="mt-1">Shared examples use the fixture clock. Refresh reloads these fixed examples and does not incorporate resource updates. {facilityDataMode === "api" ? "Hospital details open connected reports; return to Connected reports after saving an update." : "Hospital details use the browser demo; capacity previews do not include its saved observations."}</p></div>}
    {fictional && !exercise?.enabled && <p role="note" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-950">Fictional demo rules and synthetic hospitals. Requirement profiles are illustrative, not clinical staffing standards.</p>}

    {view === "plans" ? <ExerciseOverview /> : pending ? <section role="status" aria-live="polite" aria-busy="true" className={`${panelClass} p-8`}><p className="text-sm text-slate-600">{state.phase === "loading" ? "Loading services and network capacity…" : "Updating network capacity… Previous results are hidden until the refresh completes."}</p><div aria-hidden="true" className="mt-5 grid animate-pulse grid-cols-3 gap-3">{[1, 2, 3].map((id) => <div key={id} className="h-24 rounded-lg bg-slate-100" />)}</div></section>
      : state.phase === "error" ? <LoadError message={state.message} retry={refresh} />
      : state.phase === "empty" ? <EmptyNetwork title="No services available" message="Services will appear when participating hospitals report them." />
      : summaryError ? <LoadError message={summaryError} retry={refresh} />
      : ready && summary && <>
        {!ready.data.facilities.length ? <EmptyNetwork title={ready.data.service_name === null ? "Service not found" : "No hospitals offer this service"} message="Select an available service. Hospitals that do not offer this service are excluded, not counted as unavailable." />
          : !rows.length ? <EmptyNetwork title="No matching hospitals" message="Change the hospital name or capacity status filter." clear={() => updateQuery({ name: null, status: null })} />
          : <>
            {view === "map" && <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
              <section className={`${panelClass} overflow-hidden`} aria-labelledby="hospital-map-heading"><div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"><div><h2 id="hospital-map-heading" className="flex items-center gap-2 text-lg font-semibold"><Map size={18} aria-hidden="true" />Hospitals on the map</h2><p className="mt-1 text-xs text-slate-500">{rows.length} of {ready.data.facilities.length} hospitals · Select a marker for details.</p></div><p className="text-xs text-slate-500">Updated <Timestamp value={ready.data.as_of} /></p></div><HospitalMap rows={rows} returnTo={returnTo} /></section>
              <AttentionList rows={rows} attentionIds={summary.attention_facility_ids} returnTo={returnTo} />
            </div>}
            <details className={`${panelClass} p-4`}><summary className="cursor-pointer text-sm font-medium text-teal-800">Network totals and reporting coverage</summary><div className="mt-4"><SummaryCards summary={summary} /></div></details>
            {view === "hospitals" && <HospitalTable rows={rows} returnTo={returnTo} />}
          </>}
        <p className="text-xs leading-relaxed text-slate-500">Freshness threshold: {ready.data.stale_after_hours} hours · Open a hospital for resource evidence.</p>
      </>}
  </div>;
}

function EmptyNetwork({ title, message, clear }: { title: string; message: string; clear?: () => void }) {
  return <section className={`${panelClass} p-8 text-center`}><Building2 size={25} className="mx-auto text-slate-400" aria-hidden="true" /><h2 className="mt-3 font-semibold">{title}</h2><p className="mt-2 text-sm text-slate-600">{message}</p>{clear && <button className={`${secondaryClass} mt-4`} onClick={clear}>Clear filters</button>}</section>;
}
