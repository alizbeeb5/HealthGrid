"use client";

import { useEffect, useRef, useState } from "react";
import { getFacilitySnapshot, FacilityClientError } from "../../lib/api/facilities";
import type { FacilitySnapshotResponse } from "../../lib/api/feature-1";
import { BackLink, displayError, LoadError, LoadingState, Location, ModeNotice, panelClass, secondaryClass, StatusBadge, Timestamp } from "./shared";
import { ResourceGroups } from "./resource-groups";
import { ObservationForm } from "./observation-form";
import { CapacityPanel } from "./capacity-panel";
import { useCapacity } from "./use-capacity";

export function FacilityDetails({ facilityId, returnTo }: { facilityId: string; returnTo?: string }) {
  const capacity = useCapacity(facilityId);
  const [snapshot, setSnapshot] = useState<FacilitySnapshotResponse>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [notFound, setNotFound] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const requestNumber = useRef(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(undefined); setNotFound(false); setSnapshot(undefined);
    const request = ++requestNumber.current;
    (async () => {
      try { const data = await getFacilitySnapshot(facilityId); if (active && request === requestNumber.current) setSnapshot(data); }
      catch (error) { if (active) { setError(displayError(error)); setNotFound(error instanceof FacilityClientError && error.status === 404); } }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [facilityId, attempt]);

  async function refreshSnapshot() {
    const request = ++requestNumber.current;
    setRefreshing(true);
    const capacityRefresh = capacity.refresh();
    try {
      const next = await getFacilitySnapshot(facilityId);
      if (request === requestNumber.current) { setSnapshot(next); setError(undefined); }
    }
    finally {
      await capacityRefresh;
      if (request === requestNumber.current) setRefreshing(false);
    }
  }

  return <>
    <BackLink returnTo={returnTo} />
    <ModeNotice />
    {loading ? <LoadingState detail /> : notFound ? <div className={`${panelClass} p-8`}><h1 className="text-xl font-semibold">Hospital not found</h1><p className="mt-3 text-sm text-slate-600">This hospital ID is not available in the selected data source.</p></div>
      : !snapshot ? <LoadError message={error ?? "No snapshot available."} retry={() => setAttempt((value) => value + 1)} /> : <>
        <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
          <div><p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-teal-700">Operational snapshot · {snapshot.facility.facility_id}</p>
            <h1 className="text-3xl font-bold tracking-tight">{snapshot.facility.name}</h1>
            <p className="mt-3 text-sm text-slate-600"><Location latitude={snapshot.facility.latitude} longitude={snapshot.facility.longitude} /></p>
          </div>
          <button className={secondaryClass} disabled={refreshing} onClick={() => refreshSnapshot().catch((error) => setError(displayError(error)))}>{refreshing ? "Refreshing…" : "Refresh snapshot"}</button>
        </div>
        {error && <p role="alert" className="mb-5 rounded-lg bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
        <div className="mb-6 grid gap-4 sm:grid-cols-2">
          <div className={`${panelClass} px-5 py-4`}><p className="text-xs text-slate-500">Latest report received</p><p className="mt-1 text-sm font-semibold"><Timestamp value={snapshot.facility.last_reported_at} /></p></div>
          <div className={`${panelClass} px-5 py-4`}><p className="text-xs text-slate-500">Snapshot as of · local time</p><p className="mt-1 text-sm font-semibold"><Timestamp value={snapshot.as_of} /></p></div>
        </div>
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="space-y-6">
            <CapacityPanel state={capacity.state} snapshot={snapshot} onRefresh={() => void capacity.refresh()} onShowExample={capacity.showExample} />
            <section className={`${panelClass} p-5`} aria-labelledby="services-heading">
              <h2 id="services-heading" className="text-lg font-semibold">Services</h2>
              {snapshot.services.length ? <ul className="mt-4 divide-y divide-slate-100">{snapshot.services.map((service) => <li key={service.service_id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"><span className="text-sm font-medium">{service.name}</span><StatusBadge status={service.status} /></li>)}</ul>
                : <p className="mt-3 text-sm text-slate-500">No services have been listed for this hospital.</p>}
            </section>
            <ResourceGroups snapshot={snapshot} />
            <p className="text-xs leading-relaxed text-slate-500">Freshness is measured against the snapshot time. Reports older than {snapshot.stale_after_hours} hours are marked stale (demo policy). All times use your local timezone; timestamps show their UTC value on hover. Reported beds and staffing counts do not establish usable service capacity.</p>
          </div>
          <ObservationForm key={facilityId} snapshot={snapshot} onSaved={refreshSnapshot} onRefresh={refreshSnapshot} />
        </div>
      </>}
  </>;
}
