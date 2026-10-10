import Link from "next/link";
import { CircleAlert, Info } from "lucide-react";
import type { ForecastPreview } from "./demo-client";
import { panelClass, Timestamp } from "../facilities/shared";
import { forecastDate } from "./presentation";

export function ForecastAlert({ data }: { data: ForecastPreview }) {
  const gap = data.first_gap;
  if (!gap) return <section role="status" className="rounded-xl border border-teal-200 bg-teal-50 p-5 text-teal-950"><h2 className="font-semibold">No central-estimate gap in this forecast</h2><p className="mt-2 text-sm">This does not confirm spare capacity. Review uncertainty ranges and the underlying assumptions.</p></section>;
  return <section role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-5 text-amber-950" aria-labelledby="forecast-alert-heading">
    <h2 id="forecast-alert-heading" className="flex items-center gap-2 font-semibold"><CircleAlert size={19} aria-hidden="true" />First expected gap: day {gap.day_number} · <time dateTime={gap.date}>{forecastDate(gap.date)}</time></h2>
    <p className="mt-3 text-lg font-semibold">{gap.demand} expected places − {gap.capacity} modeled places → possible gap of {gap.gap} places</p>
    <p className="mt-2 text-sm">Expected simultaneous demand may exceed modeled capacity. Review resource reports and planning assumptions before taking preventive action.</p>
    <ul className="mt-3 space-y-1 text-xs">{data.alerts.map((alert) => <li key={alert.date}><time dateTime={alert.date}>{forecastDate(alert.date)}</time>: {alert.message}</li>)}</ul>
    <p className="mt-2 text-xs">The alert uses central estimates. Uncertainty may include no gap; this is not a confirmed shortage or a transfer recommendation.</p>
  </section>;
}

export function ForecastTable({ data }: { data: ForecastPreview }) {
  return <section className={`${panelClass} overflow-hidden`} aria-labelledby="forecast-table-heading">
    <div className="p-5"><h2 id="forecast-table-heading" className="text-lg font-semibold">Next seven days</h2><p className="mt-1 text-xs text-slate-500">All quantities are simultaneous service places. Bounds are uncalibrated model error bands; dates are UTC calendar days.</p></div>
    <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="sr-only">Seven-day capacity, demand and supplied estimated gaps, including capacity and demand uncertainty ranges.</caption>
      <thead className="border-y border-slate-200 bg-slate-50 text-xs text-slate-600"><tr>{["Day", "Modeled capacity", "Expected demand", "Estimated gap", "Review"].map((heading) => <th scope="col" key={heading} className="px-5 py-3 font-semibold">{heading}</th>)}</tr></thead>
      <tbody className="divide-y divide-slate-100">{data.forecast.map((point, index) => <tr key={point.date} className={point.gap > 0 ? "bg-amber-50/60" : undefined}>
        <th scope="row" className="whitespace-nowrap px-5 py-4 font-medium"><time dateTime={point.date}>{forecastDate(point.date)}</time><p className="mt-1 text-xs font-normal text-slate-500">Day {index + 1}</p></th>
        <td className="px-5 py-4"><p className="font-semibold tabular-nums">{point.capacity} places</p><p className="mt-1 text-xs text-slate-500">Range {point.capacity_lower}–{point.capacity_upper}</p></td>
        <td className="px-5 py-4"><p className="font-semibold tabular-nums">{point.demand} places</p><p className="mt-1 text-xs text-slate-500">Range {point.demand_lower}–{point.demand_upper}</p></td>
        <td className="px-5 py-4"><p className={`font-semibold tabular-nums ${point.gap > 0 ? "text-amber-900" : "text-slate-700"}`}>{point.gap} places</p></td>
        <td className="min-w-40 px-5 py-4 text-xs">{point.date === data.first_gap?.date ? <strong className="text-amber-950">First expected gap</strong> : point.gap > 0 ? "Expected gap" : "No central-estimate gap"}</td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}

export function ForecastEvidence({ data }: { data: ForecastPreview }) {
  return <section className={`${panelClass} p-5`} aria-labelledby="forecast-evidence-heading"><h2 id="forecast-evidence-heading" className="flex items-center gap-2 text-lg font-semibold"><Info size={18} aria-hidden="true" />Data and assumptions</h2>
    <dl className="mt-4 grid gap-4 text-xs sm:grid-cols-2">
      <div><dt>Generated at</dt><dd><Timestamp value={data.generated_at} /></dd></div>
      <div><dt>Latest history date (UTC)</dt><dd>{data.history.at(-1)?.date ?? "No history supplied"}</dd></div>
      <div><dt>Capacity profile</dt><dd>{data.profile_version ?? "Not configured"}</dd></div>
      <div><dt>History supplied</dt><dd>{data.history.length} days</dd></div>
    </dl>
    {data.validation && <p className="mt-4 text-xs text-slate-600">Method: {data.validation.method}. Held-out validation: {data.validation.evaluated_from}–{data.validation.evaluated_to} ({data.validation.holdout_days} days). Capacity MAE: {data.validation.capacity_mae} places; demand MAE: {data.validation.demand_mae} places.</p>}
    <p className="mt-4 text-xs text-slate-600">Sources: {[...new Set(data.history.flatMap((day) => day.sources))].join(", ") || "Not supplied"}. Synthetic sources are fictional data, even when their quality label says reported. Error bands are not calibrated confidence intervals or shortage probabilities. Exact observation timestamps and interval coverage are not supplied by this endpoint.</p>
    <p className="mt-4 text-xs text-slate-500">Demand describes simultaneous service-place need for each period, not patients arriving per day. Modeled capacity is not confirmed spare admission capacity.</p>
    <Link href={`/facilities/${encodeURIComponent(data.facility_id)}`} className="mt-4 inline-block text-sm font-semibold text-teal-800 hover:underline">Inspect hospital reports →</Link>
  </section>;
}

export function InsufficientHistory({ data }: { data: ForecastPreview }) {
  return <section className={`${panelClass} p-6`} role="status"><h2 className="text-lg font-semibold">{data.status === "not_configured" ? "Calculation profile not configured" : "Insufficient history to produce a forecast"}</h2><p className="mt-3 text-sm text-slate-600">{data.history.length} history days supplied. The API returned {data.status.replaceAll("_", " ")}; no future capacity, demand or gaps are supplied. Missing quantities remain unknown.</p></section>;
}
