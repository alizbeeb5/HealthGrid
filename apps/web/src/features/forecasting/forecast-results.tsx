"use client";
import { useI18n } from "@/lib/i18n/context";
import Link from "next/link";
import { CircleAlert, Info } from "lucide-react";
import type { ForecastPreview } from "./demo-client";
import { panelClass, Timestamp } from "../facilities/shared";
import { forecastDate } from "./presentation";

export function ForecastAlert({ data }: { data: ForecastPreview }) {
  const { t, formatLocale } = useI18n();
  const gap = data.first_gap;
  if (!gap) return <section role="status" className="rounded-xl border border-teal-200 bg-teal-50 p-5 text-teal-950"><h2 className="font-semibold">{t("No central-estimate gap in this forecast")}</h2><p className="mt-2 text-sm">{t("Review the model error bands before planning.")}</p></section>;
  return <section role="status" className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-rose-950" aria-labelledby="forecast-alert-heading">
    <h2 id="forecast-alert-heading" className="flex items-center gap-2 font-semibold"><CircleAlert size={19} aria-hidden="true" />{t("First expected gap: day ")}{t(gap.day_number)} · <time dateTime={gap.date}>{t(forecastDate(gap.date, formatLocale))}</time></h2>
    <p className="mt-3 text-xl metric-number">{t(gap.demand)}{t(" expected places − ")}{t(gap.capacity)}{t(" modeled places → possible gap of ")}{t(gap.gap)}{t(" places")}</p>
    <p className="mt-2 text-sm">{t("Review the limiting resources before choosing a response.")}</p>
    <details className="mt-3 text-xs"><summary className="cursor-pointer">{t("All projected gaps")}</summary><ul className="mt-2 space-y-1">{data.alerts.map((alert) => <li key={alert.date}><time dateTime={alert.date}>{t(forecastDate(alert.date, formatLocale))}</time>: {t(alert.message)}</li>)}</ul></details>
    <p className="mt-2 text-xs">{t("Central estimate · uncertainty may include no gap.")}</p>
  </section>;
}

export function ForecastTable({ data }: { data: ForecastPreview }) {
  const { t, formatLocale } = useI18n();
  return <section className={`${panelClass} overflow-hidden`} aria-labelledby="forecast-table-heading">
    <div className="p-5"><h2 id="forecast-table-heading" className="text-lg font-semibold">{t("Next seven days")}</h2><p className="mt-1 text-xs text-slate-500">{t("All quantities are simultaneous service places. Bounds are uncalibrated model error bands; dates are UTC calendar days.")}</p></div>
    <div className="overflow-x-auto"><table className="w-full text-start text-sm"><caption className="sr-only">{t("Seven-day capacity, demand and supplied estimated gaps, including capacity and demand uncertainty ranges.")}</caption>
      <thead className="border-y border-slate-200 bg-slate-50 text-xs text-slate-600"><tr>{["Day", "Modeled capacity", "Expected demand", "Estimated gap", "Review"].map((heading) => <th scope="col" key={heading} className="px-5 py-3 font-semibold">{t(heading)}</th>)}</tr></thead>
      <tbody className="divide-y divide-slate-100">{data.forecast.map((point, index) => <tr key={point.date} className={point.gap > 0 ? "bg-amber-50/60" : undefined}>
        <th scope="row" className="whitespace-nowrap px-5 py-4 font-medium"><time dateTime={point.date}>{t(forecastDate(point.date, formatLocale))}</time><p className="mt-1 text-xs font-normal text-slate-500">{t("Day ")}{t(index + 1)}</p></th>
        <td className="px-5 py-4"><p className="font-semibold tabular-nums">{t(point.capacity)}{t(" places")}</p><p className="mt-1 text-xs text-slate-500">{t("Range ")}{t(point.capacity_lower)}–{t(point.capacity_upper)}</p></td>
        <td className="px-5 py-4"><p className="font-semibold tabular-nums">{t(point.demand)}{t(" places")}</p><p className="mt-1 text-xs text-slate-500">{t("Range ")}{t(point.demand_lower)}–{t(point.demand_upper)}</p></td>
        <td className="px-5 py-4"><p className={`font-semibold tabular-nums ${point.gap > 0 ? "text-amber-900" : "text-slate-700"}`}>{t(point.gap)}{t(" places")}</p></td>
        <td className="min-w-40 px-5 py-4 text-xs">{point.date === data.first_gap?.date ? <strong className="text-amber-950">{t("First expected gap")}</strong> : point.gap > 0 ? t("Expected gap") : t("No central-estimate gap")}</td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}

export function ForecastEvidence({ data }: { data: ForecastPreview }) {
  const { t, formatLocale } = useI18n();
  return <section className={`${panelClass} p-5`} aria-labelledby="forecast-evidence-heading"><h2 id="forecast-evidence-heading" className="flex items-center gap-2 text-lg font-semibold"><Info size={18} aria-hidden="true" />{t("Data and assumptions")}</h2>
    <dl className="mt-4 grid gap-4 text-xs sm:grid-cols-2">
      <div><dt>{t("Generated at")}</dt><dd><Timestamp value={data.generated_at} /></dd></div>
      <div><dt>{t("Latest history date (UTC)")}</dt><dd>{t(data.history.at(-1)?.date ?? "No history supplied")}</dd></div>
      <div><dt>{t("Capacity profile")}</dt><dd>{t(data.profile_version ?? "Not configured")}</dd></div>
      <div><dt>{t("History supplied")}</dt><dd>{t(data.history.length)}{t(" days")}</dd></div>
    </dl>
    {data.validation && <p className="mt-4 text-xs text-slate-600">{t("Method: ")}{t(data.validation.method)}{t(". Held-out validation: ")}{t(data.validation.evaluated_from)}–{t(data.validation.evaluated_to)} ({t(data.validation.holdout_days)}{t(" days). Capacity MAE: ")}{t(data.validation.capacity_mae)}{t(" places; demand MAE: ")}{t(data.validation.demand_mae)}{t(" places.")}</p>}
    <p className="mt-4 text-xs text-slate-600">{t("Sources: ")}{t([...new Set(data.history.flatMap((day) => day.sources))].join(", ") || "Not supplied")}{t(". Synthetic sources are fictional data, even when their quality label says reported. Error bands are not calibrated confidence intervals or shortage probabilities. Exact observation timestamps and interval coverage are not supplied by this endpoint.")}</p>
    <p className="mt-4 text-xs text-slate-500">{t("Demand describes simultaneous service-place need for each period, not patients arriving per day. Modeled capacity is not confirmed spare admission capacity.")}</p>
    <Link href={`/facilities/${encodeURIComponent(data.facility_id)}`} className="mt-4 inline-block text-sm font-semibold text-teal-800 hover:underline">{t("Inspect hospital reports →")}</Link>
  </section>;
}

export function InsufficientHistory({ data }: { data: ForecastPreview }) {
  const { t, formatLocale } = useI18n();
  return <section className={`${panelClass} p-6`} role="status"><h2 className="text-lg font-semibold">{t(data.status === "not_configured" ? "Calculation profile not configured" : "Insufficient history to produce a forecast")}</h2><p className="mt-3 text-sm text-slate-600">{t(data.history.length)}{t(" history days supplied. The API returned ")}{t(data.status.replaceAll("_", " "))}{t("; no future capacity, demand or gaps are supplied. Missing quantities remain unknown.")}</p></section>;
}
