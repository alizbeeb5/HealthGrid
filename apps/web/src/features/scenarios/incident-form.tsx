import type { IncidentFields, ServiceOverride } from "./model";
import type { FacilitySnapshotResponse } from "../../lib/api/feature-1";
import { panelClass, secondaryClass } from "../facilities/shared";
export const inputClass = "mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-teal-700";

export function IncidentForm({ value, change, disabled, snapshots }: { snapshots: FacilitySnapshotResponse[]; value: IncidentFields; change: <K extends keyof IncidentFields>(key: K, value: IncidentFields[K]) => void; disabled: boolean }) {
  const services = [...new Map(snapshots.flatMap((hospital) => hospital.services.map((service) => [service.service_id, service.name] as const))).entries()];
  function affected(id: string, enabled: boolean) {
    change("affected_facility_ids", enabled ? [...value.affected_facility_ids, id].sort() : value.affected_facility_ids.filter((item) => item !== id));
    if (!enabled) { change("service_overrides", value.service_overrides.filter((item) => item.facility_id !== id)); change("resource_overrides", value.resource_overrides.filter((item) => item.facility_id !== id)); }
  }
  function serviceOverride(id: string, status: string) {
    const rest = value.service_overrides.filter((item) => item.facility_id !== id);
    const previous = value.service_overrides.find((item) => item.facility_id === id);
    change("service_overrides", status ? [...rest, { facility_id: id, service_id: value.service_id!, status: status as ServiceOverride["status"], restriction_note: previous?.restriction_note ?? null }] : rest);
  }
  return <fieldset disabled={disabled} className={`${panelClass} space-y-5 p-5`}><legend className="sr-only">Incident details</legend>
    <h2 className="text-lg font-semibold">Declare an incident</h2>
    <label className="block text-sm font-medium">Title<input className={inputClass} maxLength={200} value={value.title} onChange={(event) => change("title", event.target.value)} /></label>
    <label className="block text-sm font-medium">Situation report (optional)<textarea className={inputClass} rows={4} maxLength={10000} value={value.report_text ?? ""} onChange={(event) => change("report_text", event.target.value || null)} /><span className="mt-1 block text-xs font-normal text-slate-500">Manual structured entry works without AI. Use synthetic reports in this preview.</span></label>
    <label className="block text-sm font-medium">Service<select className={inputClass} value={value.service_id ?? ""} onChange={(event) => { change("service_id", event.target.value || null); change("affected_facility_ids", []); change("service_overrides", []); change("resource_overrides", []); }}><option value="">Select a service</option>{services.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
    <div className="grid gap-4 sm:grid-cols-2">{([['starts_at', 'Starts at (UTC)'], ['expected_ends_at', 'Expected end (UTC, optional)']] as const).map(([key, label]) => <label key={key} className="text-sm font-medium">{label}<input type="datetime-local" className={inputClass} value={value[key]?.slice(0, 16) ?? ""} onChange={(event) => change(key, event.target.value ? `${event.target.value}:00Z` : null)} /></label>)}</div>
    <div><p className="text-sm font-medium">Affected hospitals</p><div className="mt-3 flex flex-wrap gap-4">{snapshots.filter((hospital) => hospital.services.some((service) => service.service_id === value.service_id)).map((hospital) => <label className="flex items-center gap-2 text-sm" key={hospital.facility.facility_id}><input type="checkbox" checked={value.affected_facility_ids.includes(hospital.facility.facility_id)} onChange={(event) => affected(hospital.facility.facility_id, event.target.checked)} />{hospital.facility.name}</label>)}</div></div>
    {value.affected_facility_ids.map((id) => {
      const hospital = snapshots.find((item) => item.facility.facility_id === id)!;
      const override = value.service_overrides.find((item) => item.facility_id === id);
      return <div key={id} className="space-y-4 rounded-lg border border-slate-200 p-4"><h3 className="font-semibold">{hospital.facility.name} assumptions</h3>
        <label className="block text-sm">Service state after incident<select className={inputClass} value={override?.status ?? ""} onChange={(event) => serviceOverride(id, event.target.value)}><option value="">Keep baseline service state</option><option value="operating">Operating</option><option value="limited">Limited — modeled capacity unknown</option><option value="unavailable">Unavailable</option></select></label>
        {override && <label className="block text-sm">Restriction / outage note {override.status === "limited" ? "(required)" : "(optional)"}<input className={inputClass} value={override.restriction_note ?? ""} onChange={(event) => change("service_overrides", value.service_overrides.map((item) => item.facility_id === id ? { ...item, restriction_note: event.target.value || null } : item))} /></label>}
        <details><summary className="cursor-pointer text-sm font-medium text-teal-800">Resource assumptions (absolute quantities)</summary><p className="mt-3 text-xs text-slate-500">Omitted resources retain the baseline. Explicit zero means none; these entries never update hospital reports. Resources outside the requirement profile may have no effect.</p>
          {hospital.resources.map((resource) => {
            const item = value.resource_overrides.find((entry) => entry.facility_id === id && entry.resource_id === resource.resource_id);
            const rest = value.resource_overrides.filter((entry) => !(entry.facility_id === id && entry.resource_id === resource.resource_id));
            return <div key={resource.resource_id} className="mt-4"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!item} onChange={(event) => change("resource_overrides", event.target.checked ? [...rest, { facility_id: id, resource_id: resource.resource_id, unit: resource.unit, available_quantity: NaN }] : rest)} />Override {resource.name} ({resource.unit})</label>{item && <label className="block text-xs text-slate-600">Absolute available quantity ({resource.unit})<input type="number" min={0} step={resource.allows_fractional ? "any" : 1} className={inputClass} value={Number.isFinite(item.available_quantity) ? item.available_quantity : ""} onChange={(event) => change("resource_overrides", [...rest, { ...item, available_quantity: event.target.value === "" ? NaN : Number(event.target.value) }])} /></label>}</div>;
          })}
        </details>
      </div>;
    })}
    <div><p className="text-sm font-medium">Additional assumptions</p>{value.assumptions.map((assumption, index) => <div key={index} className="mt-2 flex items-center gap-2"><input aria-label={`Assumption ${index + 1}`} className={inputClass} maxLength={500} value={assumption} onChange={(event) => change("assumptions", value.assumptions.map((item, i) => i === index ? event.target.value : item))} /><button type="button" className={secondaryClass} onClick={() => change("assumptions", value.assumptions.filter((_, i) => i !== index))}>Remove</button></div>)}<button type="button" className={`${secondaryClass} mt-3`} onClick={() => change("assumptions", [...value.assumptions, ""])}>Add assumption</button></div>
  </fieldset>;
}
