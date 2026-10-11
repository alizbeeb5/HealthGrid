"use client";
import { PageHeader } from "../exercise/page-header";
import { NextStep } from "../exercise/journey";
import { useExercise } from "../exercise/context";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, RefreshCw, TrendingUp } from "lucide-react";
import { buttonClass, LoadError, panelClass } from "../facilities/shared";
import { forecastCatalog, getForecastExample, getForecast, loadForecastCatalog } from "./demo-client";
import { createForecastLoader, type ForecastState } from "./forecast-loader";
import { ForecastAlert, ForecastEvidence, ForecastTable, InsufficientHistory } from "./forecast-results";
import { forecastDate } from "./presentation";

const ForecastChart = dynamic(() => import("./forecast-chart"), { ssr: false, loading: () => <p role="status" className="p-8 text-sm text-slate-600">Loading forecast chart… Exact values are available in the table below.</p> });
const inputClass = "mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-teal-700 focus:outline-2 focus:outline-teal-100";

export function ForecastDashboard() {
  const exercise = useExercise();
  const params = useSearchParams();
  const [attempt, setAttempt] = useState(0);
  const [view, setView] = useState<"chart" | "table">("chart");
  const mode = !exercise?.enabled && params.get("mode") === "example" ? "example" : "api";
  const [catalog, setCatalog] = useState<ReturnType<typeof forecastCatalog>>([]);
  const [catalogError, setCatalogError] = useState<string>();
  useEffect(() => {
    let active = true;
    setCatalog([]); setCatalogError(undefined);
    void loadForecastCatalog(mode).then((items) => { if (active) setCatalog(items); }).catch((error) => { if (active) setCatalogError(error instanceof Error ? error.message : "Could not load hospital catalog."); });
    return () => { active = false; };
  }, [mode, attempt]);
  const facilityId = params.get("facility_id") ?? (exercise?.enabled ? "BEI-WEST" : catalog[0]?.facility.facility_id ?? "DEMO-B");
  const hospital = catalog.find((item) => item.facility.facility_id === facilityId);
  const serviceId = params.get("service_id") ?? hospital?.services.find((service) => service.service_id === "emergency-care")?.service_id ?? hospital?.services[0]?.service_id ?? "emergency-care";
  const service = hospital?.services.find((item) => item.service_id === serviceId);
  const [state, setState] = useState<ForecastState>({ phase: "loading" });

  const loader = useMemo(() => createForecastLoader(mode === "example" ? getForecastExample : getForecast, setState), [mode]);
  const refresh = useCallback(() => { loader.cancel(); setState({ phase: "updating" }); setAttempt((value) => value + 1); }, [loader]);
  useEffect(() => {
    void loader.refresh(facilityId, serviceId);
    return () => loader.cancel();
  }, [loader, facilityId, serviceId, attempt]);

  function select(changes: Record<string, string>) {
    loader.cancel(); setState({ phase: "updating" });
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(changes)) next.set(key, value);
    window.history.replaceState(null, "", `/forecasts?${next}`);
  }
  const data = state.phase === "ready" && state.data.facility_id === facilityId && state.data.service_id === serviceId ? state.data : undefined;
  const pending = state.phase === "loading" || state.phase === "updating" || (state.phase === "ready" && !data);

  return <div className="space-y-4">
    <PageHeader title="Capacity forecast" description="Seven-day demand, capacity and potential gaps." actions={<button className={buttonClass} disabled={pending} onClick={refresh}><RefreshCw size={16} aria-hidden="true" />{pending ? "Refreshing…" : "Refresh"}</button>} />

    {catalogError && <LoadError message={catalogError} retry={refresh} />}
    <section className={`${panelClass} grid gap-4 p-5 ${exercise?.enabled ? "" : "sm:grid-cols-2"}`} aria-label="Forecast selection">
      <label className="text-xs font-semibold text-slate-600">Hospital<select className={inputClass} value={facilityId} onChange={(event) => {
        const next = catalog.find((item) => item.facility.facility_id === event.target.value);
        const nextService = next?.services.find((item) => item.service_id === "emergency-care") ?? next?.services[0];
        select({ facility_id: event.target.value, service_id: nextService?.service_id ?? "" });
      }}>{!hospital && <option value={facilityId}>Hospital not listed ({facilityId})</option>}{catalog.map((item) => <option key={item.facility.facility_id} value={item.facility.facility_id}>{item.facility.name}</option>)}</select></label>
      {!exercise?.enabled && <label className="text-xs font-semibold text-slate-600">Service<select className={inputClass} value={serviceId} onChange={(event) => select({ service_id: event.target.value })} disabled={!hospital?.services.length}>{!service && <option value={serviceId}>Service not listed ({serviceId})</option>}{hospital?.services.map((item) => <option key={item.service_id} value={item.service_id}>{item.name}</option>)}</select></label>}
    </section>

    {pending ? <ForecastLoading updating={state.phase !== "loading"} />
      : state.phase === "error" ? <LoadError message={state.message} retry={refresh} />
      : data && <>
        <div><h2 className="text-xl font-semibold">{hospital?.facility.name ?? data.facility_id} · {service?.name ?? data.service_id}</h2><p className="mt-1 text-xs text-slate-500">Single service · simultaneous service places</p></div>
        {data.status !== "forecasted" ? <InsufficientHistory data={data} /> : <>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className={`${panelClass} p-5`}><p className="text-xs text-slate-500">Latest historical capacity</p><p className="mt-3 text-3xl font-semibold">{data.baseline_capacity === null ? "Unknown" : `${data.baseline_capacity} places`}</p></div>
            <div className={`${panelClass} p-5`}><p className="flex items-center gap-2 text-xs text-slate-500"><CalendarDays size={15} aria-hidden="true" />Forecast horizon</p><p className="mt-3 text-3xl font-semibold">Seven days</p><p className="mt-2 text-xs text-slate-500">{data.forecast[0] && forecastDate(data.forecast[0].date)}–{data.forecast.at(-1) && forecastDate(data.forecast.at(-1)!.date)}</p></div>
            <div className={`${panelClass} p-5`}><p className="text-xs text-slate-500">First projected gap</p><p className="mt-3 text-3xl font-semibold">{data.first_gap ? `${data.first_gap.gap} places` : "None"}</p><p className="mt-2 text-xs text-slate-500">{data.first_gap ? `Day ${data.first_gap.day_number} · ${forecastDate(data.first_gap.date)}` : "Review uncertainty ranges"}</p></div>
          </div>
          <ForecastAlert data={data} />
          <div role="group" aria-label="Forecast view" className="inline-flex gap-1 rounded-lg border border-slate-200 bg-white p-1">{([['chart', 'Chart'], ['table', 'Daily values']] as const).map(([key, label]) => <button key={key} aria-pressed={view === key} onClick={() => setView(key)} className={`rounded-md px-4 py-2 text-sm font-medium ${view === key ? "bg-teal-50 text-teal-900" : "text-slate-500 hover:bg-slate-50"}`}>{label}</button>)}</div>
          {view === "chart" ? <section className={`${panelClass} p-5`} aria-labelledby="forecast-chart-heading"><h2 id="forecast-chart-heading" className="flex items-center gap-2 text-lg font-semibold"><TrendingUp size={19} aria-hidden="true" />History and seven-day forecast</h2><p className="mt-2 text-xs text-slate-500">Solid: history · Dashed: forecast · Shaded: model error bands. Units: simultaneous treatment places.</p><div className="mt-5"><ForecastChart data={data} /></div></section> : <ForecastTable data={data} />}
          <details className={`${panelClass} p-5`}><summary className="cursor-pointer text-sm font-semibold text-teal-800">Historical records</summary><div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Historical simultaneous capacity and demand</caption><thead><tr>{["Date", "Modeled capacity", "Demand", "Sources / quality"].map((heading) => <th scope="col" key={heading} className="py-2 pr-4 text-xs text-slate-500">{heading}</th>)}</tr></thead><tbody>{data.history.map((point) => <tr key={point.date} className="border-t border-slate-100"><th scope="row" className="py-2 pr-4 font-normal"><time dateTime={point.date}>{forecastDate(point.date)}</time></th><td className="py-2 pr-4">{point.capacity === null ? "Unknown" : `${point.capacity} places`}</td><td className="py-2">{point.demand === null ? "Unknown" : `${point.demand} places`}</td><td className="py-2 text-xs">{point.sources.join(", ") || "Unknown source"} · {point.data_quality ?? "Unknown quality"}</td></tr>)}</tbody></table></div></details>
        </>}
        <details className={`${panelClass} p-5`}><summary className="cursor-pointer text-sm font-medium text-teal-800">Method and evidence</summary><div className="mt-4"><ForecastEvidence data={data} /></div></details>
      </>}
    {exercise?.enabled && <NextStep to="scenarios">Review the sudden incident with AI</NextStep>}
  </div>;
}

export function ForecastLoading({ updating }: { updating: boolean }) {
  return <section role="status" aria-live="polite" aria-busy="true" className={`${panelClass} p-8`}><p className="text-sm text-slate-600">{updating ? "Updating forecast… Previous results are hidden while this selection loads." : "Loading forecast…"}</p><div aria-hidden="true" className="mt-5 h-48 animate-pulse rounded-lg bg-slate-100" /></section>;
}
