"use client";

import { Gauge, Info } from "lucide-react";
import type { FacilitySnapshotResponse } from "../../lib/api/feature-1";
import type { ServiceCapacityResult } from "../../lib/api/feature-2";
import type { CapacityState } from "./capacity-loader";
import { panelClass, secondaryClass, StatusBadge, Timestamp } from "./shared";

const reasons: Record<string, string> = {
  service_unavailable: "The service is reported as unavailable. Its modeled capacity is zero, regardless of resource freshness.",
  requirements_not_configured: "No resource requirement profile has been configured for this service.",
  service_restriction_unquantified: "The service is limited, but the restriction has not been quantified. Its capacity cannot be estimated from these reports.",
  missing_required_observation: "One or more required resources have no observation. Missing information cannot be treated as zero.",
  stale_required_observation: "One or more required observations are outdated and cannot support a current estimate.",
};

function formatQuantity(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 20 });
}

function ServiceResult({ result, snapshot }: { result: ServiceCapacityResult; snapshot: FacilitySnapshotResponse }) {
  const resourceName = (id: string) => snapshot.resources.find((item) => item.resource_id === id)?.name ?? id;
  const serviceName = snapshot.services.find((item) => item.service_id === result.service_id)?.name ?? result.service_id;
  const calculated = result.status === "calculated";
  const labels: Record<string, string> = { calculated: "Estimated", unknown: "Cannot determine", unavailable: "Service unavailable", not_configured: "Not configured" };

  return <article className="border-t border-slate-200 p-5 first:border-t-0">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="font-semibold">{serviceName}</h3>
      <span className="flex items-center gap-2 text-xs text-slate-500">Service status <StatusBadge status={result.service_status} /></span>
    </div>
    <div className="mt-5 grid gap-4 sm:grid-cols-2">
      <div className="rounded-lg bg-teal-50 p-4">
        <p className="text-xs font-semibold text-teal-900">Modeled service places</p>
        <p className="mt-2 text-3xl font-bold tabular-nums text-teal-950" aria-label={result.estimated_capacity === null ? "Capacity cannot be determined" : `${result.estimated_capacity} simultaneous service places`}>
          {result.estimated_capacity === null ? <span className="text-xl">{labels[result.status] ?? "Cannot determine"}</span> : formatQuantity(result.estimated_capacity)}
        </p>
        <p className="mt-2 text-xs text-teal-900">{result.estimated_capacity === null ? "No numerical estimate is available." : `Simultaneous service places · ${labels[result.status] ?? result.status}`}</p>
      </div>
      <div className="rounded-lg border border-slate-200 p-4">
        <p className="text-xs font-semibold text-slate-500">{result.bottleneck_resource_ids.length > 1 ? "Bottlenecks (tied)" : "Bottleneck"}</p>
        <p className="mt-2 text-sm font-semibold">{calculated && result.bottleneck_resource_ids.length ? result.bottleneck_resource_ids.map(resourceName).join(", ") : "Not identified"}</p>
        <p className="mt-2 text-xs text-slate-500">{calculated ? "Limits the resource-based estimate." : "Only a calculated estimate identifies limiting resources."}</p>
      </div>
    </div>
    {result.reason_codes.length > 0 && <ul aria-label="Capacity explanations" className="mt-4 space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
      {result.reason_codes.map((reason) => <li key={reason}>{reasons[reason] ?? `Capacity could not be determined: ${reason.replaceAll("_", " ")}.`}</li>)}
    </ul>}
    <div className="mt-5"><h4 className="text-sm font-semibold">Resources and assumptions</h4>
      <p className="mt-1 text-xs text-slate-500">Each resource limit is the quantity divided by its requirement per place, rounded down. The estimate uses the smallest usable limit.</p>
    </div>
    {result.resource_limits.length ? <ul className="mt-3 divide-y divide-slate-100">
      {result.resource_limits.map((resource) => <li key={resource.resource_id} className="py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold">{resourceName(resource.resource_id)}{calculated && result.bottleneck_resource_ids.some((id) => id === resource.resource_id) && <span className="ml-2 rounded bg-teal-100 px-2 py-0.5 text-xs text-teal-900">Bottleneck</span>}</span>
          <StatusBadge status={resource.data_status} />
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
          <div><dt className="text-slate-500">Reported quantity</dt><dd className="mt-1 font-medium">{resource.available_quantity === null ? "Unknown" : formatQuantity(resource.available_quantity)} {resource.unit}</dd></div>
          <div><dt className="text-slate-500">Required per place</dt><dd className="mt-1 font-medium">{formatQuantity(resource.required_per_capacity_unit)} {resource.unit}</dd></div>
          <div><dt className="text-slate-500">Resource limit</dt><dd className="mt-1 font-medium">{resource.capacity_limit === null ? "Cannot determine" : `${formatQuantity(resource.capacity_limit)} places`}</dd></div>
        </dl>
        {resource.capacity_limit !== null && resource.available_quantity !== null && <p className="mt-2 text-xs text-slate-500">{formatQuantity(resource.available_quantity)} ÷ {formatQuantity(resource.required_per_capacity_unit)} → {formatQuantity(resource.capacity_limit)} places (rounded down)</p>}
        <p className="mt-3 text-xs text-slate-500">Observed: <Timestamp value={resource.observed_at} /></p>
        <p className="mt-1 break-all text-xs text-slate-500">Observation: {resource.observation_id ?? "No observation"}</p>
      </li>)}
    </ul> : <p className="mt-3 text-sm text-slate-500">No resource requirements are configured.</p>}
    <p className="mt-3 text-xs text-slate-500">Requirement profile: {result.profile_version ?? "Not configured"}. Only resources listed in this profile contribute to this estimate.</p>
    {result.profile_version?.startsWith("demo-") && <p className="mt-2 text-xs font-medium text-amber-900">Fictional demo rules; these requirements are not clinical staffing standards.</p>}
  </article>;
}

export function CapacityPanel({ state, snapshot, onRefresh, onShowExample }: {
  state: CapacityState;
  snapshot: FacilitySnapshotResponse;
  onRefresh: () => void;
  onShowExample?: () => void;
}) {
  const pending = state.phase === "loading" || state.phase === "updating";
  return <section className={`${panelClass} overflow-hidden`} aria-labelledby="capacity-heading" aria-busy={pending}>
    <div className="flex items-start justify-between gap-3 border-b border-slate-100 p-5">
      <div><h2 id="capacity-heading" className="flex items-center gap-2 text-lg font-semibold"><Gauge size={19} className="text-teal-800" aria-hidden="true" />Current capacity and bottlenecks</h2>
        <p className="mt-1 text-xs text-slate-500">Resource-based estimates for each service.</p>
      </div>
      <button className={secondaryClass} onClick={onRefresh} disabled={pending}>Refresh</button>
    </div>
    {pending ? <div role="status" aria-live="polite" className="p-5"><p className="text-sm text-slate-600">{state.phase === "updating" ? "Updating capacity from the latest reports… Previous results are hidden until the refresh completes." : "Loading capacity…"}</p><div aria-hidden="true" className="mt-4 h-20 animate-pulse rounded-lg bg-slate-100" /></div>
      : state.phase === "error" ? <div className="p-5"><div role="alert"><h3 className="font-semibold">Capacity could not be loaded</h3><p className="mt-2 text-sm text-slate-600">{state.message}</p></div>
        <button className={`${secondaryClass} mt-4`} onClick={onRefresh}>Try again</button>
        {onShowExample && <button className={`${secondaryClass} ml-2 mt-4`} onClick={onShowExample}>View synthetic example</button>}
      </div> : state.phase === "ready" && <>
        {state.source === "example" && <div role="note" className="border-b border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-950"><strong>Synthetic capacity example</strong><p className="mt-1">This is a frozen example of the capacity response. It does not reflect saved resource updates or the current hospital snapshot.</p></div>}
        <div className="bg-slate-50 px-5 py-3 text-xs text-slate-600">Capacity as of: <Timestamp value={state.data.as_of} /> · Reports older than {state.data.stale_after_hours} hours are stale.</div>
        {state.data.services.length ? <div>{state.data.services.map((service) => <ServiceResult key={service.service_id} result={service} snapshot={snapshot} />)}</div>
          : <p className="p-5 text-sm text-slate-600">No services are configured for this hospital.</p>}
        <div className="flex gap-2 border-t border-slate-100 bg-slate-50 p-5 text-xs leading-relaxed text-slate-600"><Info size={16} className="mt-0.5 shrink-0" aria-hidden="true" /><p>Each service is modeled separately using hospital-wide resources. Do not add estimates across services sharing staff or equipment. This estimate is not confirmed spare admission capacity or a clinically validated capacity assessment.</p></div>
      </>}
  </section>;
}
