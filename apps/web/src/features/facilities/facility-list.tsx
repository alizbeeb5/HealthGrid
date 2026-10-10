"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, Building2, Search } from "lucide-react";
import { listFacilities } from "../../lib/api/facilities";
import type { Facility } from "../../lib/api/feature-1";
import { displayError, LoadError, LoadingState, Location, ModeNotice, panelClass, secondaryClass, Timestamp } from "./shared";

export function FacilityList() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true); setError(undefined);
    (async () => {
      try { const data = await listFacilities(); if (active) setFacilities(data.items); }
      catch (error) { if (active) setError(displayError(error)); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [attempt]);
  const matches = facilities.filter((facility) => `${facility.name} ${facility.facility_id} ${facility.latitude} ${facility.longitude}`.toLowerCase().includes(query.toLowerCase().trim()));

  return <>
    <div className="mb-7">
      <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-teal-700">Operations / Facilities</p>
      <h1 className="text-3xl font-bold tracking-tight">Hospitals</h1>
      <p className="mt-2 text-slate-600">Inspect services, review reported resources, and record an observation.</p>
    </div>
    <ModeNotice />
    {loading ? <LoadingState /> : error ? <LoadError message={error} retry={() => setAttempt((value) => value + 1)} /> : <>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-slate-600">{facilities.length} {facilities.length === 1 ? "hospital" : "hospitals"} · Times in your local timezone</p>
        <label className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus-within:border-teal-700 focus-within:ring-2 focus-within:ring-teal-100">
          <Search size={16} className="text-slate-400" aria-hidden="true" />
          <span className="sr-only">Search hospitals</span>
          <input className="w-56 bg-transparent outline-none" type="search" placeholder="Search name, ID, or location" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
      </div>
      {!matches.length ? <div className={`${panelClass} p-10 text-center`}>
        <Building2 className="mx-auto mb-3 text-slate-400" size={28} aria-hidden="true" />
        <h2 className="font-semibold">{facilities.length ? "No matching hospitals" : "No hospitals available"}</h2>
        <p className="mt-2 text-sm text-slate-600">{facilities.length ? "Try a different name, ID, or location." : "Hospitals will appear here once they are available in the data source."}</p>
        <button className={`${secondaryClass} mt-5`} onClick={() => { setQuery(""); setAttempt((value) => value + 1); }}>{facilities.length ? "Clear search" : "Refresh list"}</button>
      </div> : <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {matches.map((facility) => <Link key={facility.facility_id} href={`/facilities/${encodeURIComponent(facility.facility_id)}`}
          className={`${panelClass} group p-6 transition hover:border-teal-500 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700`}>
          <div className="mb-6 flex items-center justify-between"><span className="rounded-lg bg-teal-50 p-2.5 text-teal-800"><Building2 size={22} aria-hidden="true" /></span>
            <ArrowUpRight size={18} className="text-slate-400 group-hover:text-teal-700" aria-hidden="true" /></div>
          <p className="mb-1 text-xs font-semibold tracking-wider text-slate-500">{facility.facility_id}</p>
          <h2 className="text-lg font-semibold">{facility.name}</h2>
          <div className="mt-3 text-xs text-slate-600"><Location latitude={facility.latitude} longitude={facility.longitude} /></div>
          <div className="mt-6 border-t border-slate-100 pt-4"><p className="mb-1 text-xs text-slate-500">Latest report received</p>
            <p className="text-sm font-medium"><Timestamp value={facility.last_reported_at} /></p></div>
          <p className="mt-5 text-sm font-semibold text-teal-800">View operational snapshot <span aria-hidden="true">→</span></p>
        </Link>)}
      </div>}
      <p className="mt-5 text-xs text-slate-500">Latest reporting time is the receipt of any observation. Individual resources can still be stale or unreported.</p>
    </>}
  </>;
}
