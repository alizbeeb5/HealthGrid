import Link from "next/link";
import { CircleAlert } from "lucide-react";
import type { NetworkFacilityResult } from "../../lib/api/network";
import { panelClass } from "../facilities/shared";
import { CapacityBadge, ModeledPlaces } from "./hospital-table";
import { evidenceWarnings, facilityLink } from "./presentation";

/** Order and inclusion come from teammate 3's summary output, not a UI policy. */
export function AttentionList({ rows, attentionIds, returnTo }: { rows: NetworkFacilityResult[]; attentionIds: string[]; returnTo: string }) {
  const byId = new Map(rows.map((row) => [row.facility.facility_id, row]));
  const attention = attentionIds.flatMap((id) => { const row = byId.get(id); return row ? [row] : []; });
  return <section className={`${panelClass} p-5`} aria-labelledby="attention-heading">
    <h2 id="attention-heading" className="flex items-center gap-2 text-lg font-semibold"><CircleAlert size={19} className="text-amber-700" aria-hidden="true" />Needs attention</h2>
    <p className="mt-1 text-xs text-slate-500">Operational review categories. Positive modeled estimates are not evidence of a shortage.</p>
    {attention.length === 0 ? <p className="mt-4 text-sm text-slate-600">No hospitals in this selection are flagged for operational review.</p>
      : <ul className="mt-4 divide-y divide-slate-100">{attention.map((row) => <li key={row.facility.facility_id} className="py-4 first:pt-0 last:pb-0">
        <div className="flex flex-wrap items-center justify-between gap-2"><Link href={facilityLink(row.facility.facility_id, returnTo)} className="font-semibold text-teal-800 hover:underline">{row.facility.name}</Link><CapacityBadge row={row} /></div>
        <p className="mt-2 text-sm"><ModeledPlaces row={row} /></p>
        <ul className="mt-2 space-y-1 text-xs text-slate-600">{evidenceWarnings(row).map((warning) => <li key={warning}>{warning}</li>)}</ul>
        <p className="mt-2 text-xs text-teal-800">Open the hospital to inspect reports and record an update.</p>
      </li>)}</ul>}
  </section>;
}
