import type { FacilitySnapshotResponse } from "../../lib/api/feature-1";
import { StatusBadge, Timestamp, panelClass } from "./shared";

const groups = [
  { name: "Emergency care", ids: ["available-beds", "nurses-on-duty", "emergency-physicians", "working-monitors", "functional-oxygen-points"], note: "These resources constrain the Beirut exercise's emergency stabilization estimate." },
  { name: "Surgery & diagnostics", ids: ["operating-theatres", "surgeons-on-duty", "anesthetists-on-duty", "sterile-surgical-kits", "working-ct-scanners", "working-xray-units"], note: "Reported operational context; surgical throughput is not calculated from these counts." },
  { name: "Trauma & respiratory supplies", ids: ["trauma-dressing-kits", "rbc-o-positive", "rbc-o-negative", "working-ventilators", "oxygen-stock"], note: "Stock and equipment reports. Consumption duration, blood compatibility and patient suitability require separate assessment." },
  { name: "Transport & power", ids: ["available-ambulances", "generator-fuel", "working-generators"], note: "Reported response dependencies. Fuel duration and vehicle dispatch schedules are not inferred." },
];
export function ResourceGroups({ snapshot }: { snapshot: FacilitySnapshotResponse }) {
  const beirut = snapshot.facility.facility_id.startsWith("BEI-");
  const known = new Set(groups.flatMap((g) => g.ids));
  const sections = [...groups.map((group) => ({ ...group, resources: snapshot.resources.filter((r) => group.ids.includes(r.resource_id)) })), { name: "Other reported resources", note: "Reported quantities and observation times.", resources: snapshot.resources.filter((r) => !known.has(r.resource_id)) }].filter((g) => g.resources.length);
  return <section className={`${panelClass} overflow-hidden`} aria-labelledby="resources-heading"><div className="border-b border-slate-100 p-5"><h2 id="resources-heading" className="text-lg font-semibold">Resources by care need</h2><p className="mt-2 text-sm text-slate-500">Open a group to inspect quantities and freshness. Unknown means no report; zero is a reported quantity.</p></div>
    {sections.map((group, index) => <details key={group.name} open={index === 0} className="group border-b border-slate-100 last:border-0"><summary className="flex cursor-pointer items-center justify-between p-5 text-sm font-semibold hover:bg-slate-50"><span>{group.name}</span><span className="text-xs font-normal text-slate-500">{group.resources.length} resources · expand</span></summary><p className="px-5 pb-4 text-xs leading-5 text-slate-500">{beirut ? group.note : "Only resources in the configured service profile contribute to its capacity estimate."}</p><ul className="grid gap-3 px-5 pb-5 sm:grid-cols-2">{group.resources.map((r) => <li key={r.resource_id} className="rounded-lg border border-slate-200 p-4"><div className="flex flex-wrap items-start justify-between gap-2"><h3 className="max-w-52 text-sm font-medium">{r.name}</h3><StatusBadge status={r.data_status} /></div><p className="my-3 text-2xl font-semibold tabular-nums">{r.available_quantity === null ? "Unknown" : r.available_quantity.toLocaleString()} <span className="text-xs font-normal text-slate-500">{r.unit}</span></p><p className="text-xs text-slate-500">Observed <Timestamp value={r.observed_at} /></p></li>)}</ul></details>)}
  </section>;
}
