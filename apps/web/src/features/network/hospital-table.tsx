import { useExerciseNames } from "../exercise/context";
import Link from "next/link";
import type { NetworkFacilityResult } from "../../lib/api/network";
import { panelClass, Timestamp } from "../facilities/shared";
import { capacityLabels, evidenceWarnings, facilityLink } from "./presentation";

export function CapacityBadge({ row }: { row: NetworkFacilityResult }) {
  const colors = { calculated: "bg-teal-50 text-teal-900 ring-teal-200", unknown: "bg-amber-50 text-amber-900 ring-amber-200", unavailable: "bg-rose-50 text-rose-900 ring-rose-200", not_configured: "bg-slate-100 text-slate-700 ring-slate-200" };
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${colors[row.capacity.status]}`}>{capacityLabels[row.capacity.status]}</span>;
}

export function ModeledPlaces({ row }: { row: NetworkFacilityResult }) {
  return <span className="font-semibold tabular-nums">{row.capacity.estimated_capacity === null ? "Not determined" : `${row.capacity.estimated_capacity.toLocaleString()} modeled places`}</span>;
}

export function HospitalTable({ rows, returnTo }: { rows: NetworkFacilityResult[]; returnTo: string }) {
  const { resource: resourceLabel } = useExerciseNames();
  return <section className={`${panelClass} overflow-hidden`} aria-labelledby="hospital-table-heading">
    <div className="p-5"><h2 id="hospital-table-heading" className="text-lg font-semibold">Hospital comparison</h2><p className="mt-1 text-xs text-slate-500">Latest report is a receipt time; individual resources can still be missing or stale.</p></div>
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm"><caption className="sr-only">Filtered hospitals offering the selected service, their modeled capacity and evidence warnings.</caption>
        <thead className="border-y border-slate-200 bg-slate-50 text-xs text-slate-600"><tr>{["Hospital", "Modeled places / status", "Bottleneck", "Evidence / assumptions", "Latest report received"].map((heading) => <th scope="col" key={heading} className="px-5 py-3 font-semibold">{heading}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100">{rows.map((row) => <tr key={row.facility.facility_id} className="align-top">
          <th scope="row" className="px-5 py-5 font-normal"><Link className="font-semibold text-teal-800 hover:underline" href={facilityLink(row.facility.facility_id, returnTo)}>{row.facility.name}<span className="sr-only">: open hospital details</span></Link><p className="mt-1 text-xs text-slate-500">{row.facility.facility_id}</p></th>
          <td className="px-5 py-5"><ModeledPlaces row={row} /><div className="mt-2"><CapacityBadge row={row} /></div><p className="mt-2 text-xs text-slate-500">Service: {row.capacity.service_status}</p></td>
          <td className="px-5 py-5">{row.capacity.bottleneck_resource_ids.length ? row.capacity.bottleneck_resource_ids.map((id) => <p key={id} className="mb-1">{resourceLabel(id)}</p>) : <span className="text-slate-500">Not identified</span>}</td>
          <td className="min-w-56 px-5 py-5"><EvidenceDetails row={row} /></td>
          <td className="min-w-44 px-5 py-5 text-xs"><Timestamp value={row.facility.last_reported_at} /></td>
        </tr>)}</tbody>
      </table>
    </div>
  </section>;
}

export function EvidenceDetails({ row }: { row: NetworkFacilityResult }) {
  const { resource: resourceLabel } = useExerciseNames();
  const warnings = evidenceWarnings(row);
  return <>
    {warnings.length ? <ul className="space-y-1 text-xs text-amber-950">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p className="text-xs text-slate-500">Required reports are current.</p>}
    <p className="mt-2 text-xs text-slate-500">Profile: {row.capacity.profile_version ?? "Not configured"}</p>
    {row.capacity.resource_limits.length > 0 && <details className="mt-3 text-xs"><summary className="cursor-pointer font-medium text-teal-800">View resource evidence</summary>
      <ul className="mt-3 space-y-3">{row.capacity.resource_limits.map((resource) => <li key={resource.resource_id}>
        <p className="font-semibold">{resourceLabel(resource.resource_id)} · {resource.data_status}</p>
        <p className="mt-1">{resource.available_quantity === null ? "Unknown quantity" : resource.available_quantity.toLocaleString(undefined, { maximumFractionDigits: 20 })} {resource.unit} · {resource.required_per_capacity_unit} {resource.unit} required per place</p>
        <p className="mt-1">Resource limit: {resource.capacity_limit === null ? "Not determined" : `${resource.capacity_limit} places`}</p>
        <p className="mt-1">Observed: <Timestamp value={resource.observed_at} /></p><p className="mt-1 break-all text-slate-500">Observation: {resource.observation_id ?? "No observation"}</p>
      </li>)}</ul>
    </details>}
  </>;
}
