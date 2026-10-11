"use client";
import type { ReactNode } from "react";
import { useI18n } from "@/lib/i18n/context";

export type MetricTone = "capacity" | "gap" | "funding" | "neutral";
const tones: Record<MetricTone, string> = {
  capacity: "border-teal-200 bg-teal-50 text-teal-950",
  gap: "border-rose-200 bg-rose-50 text-rose-950",
  funding: "border-blue-200 bg-blue-50 text-blue-950",
  neutral: "border-slate-200 bg-white text-slate-900",
};
/** Tone supplements the visible metric label; missing quantities remain explicit. */
export function MetricCard({ label, value, detail, tone = "neutral" }: {
  label: string; value: ReactNode; detail?: ReactNode; tone?: MetricTone;
}) {
  const { t } = useI18n();
  return <div className={`rounded-xl border p-5 shadow-sm ${tones[tone]}`}>
    <p className="text-sm font-semibold">{t(label)}</p>
    <p className="metric-value mt-3">{t(value)}</p>
    {detail !== undefined && <p className="mt-2 text-xs leading-5">{t(detail)}</p>}
  </div>;
}
