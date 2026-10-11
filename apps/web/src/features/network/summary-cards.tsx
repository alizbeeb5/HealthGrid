"use client";
import { useI18n } from "@/lib/i18n/context";
import { Building2, ChartNoAxesCombined } from "lucide-react";
import { panelClass } from "../facilities/shared";
import type { NetworkSummary } from "./summary";

export function SummaryCards({ summary }: { summary: NetworkSummary }) {
  const { t } = useI18n();
  const cards = [
    ["Reporting hospitals", summary.facility_count],
    ["Capacity assessed", summary.calculated_count],
    ["Reports need clarification", summary.unknown_count],
    ["Services interrupted", summary.unavailable_count],
    ["Assessment rules needed", summary.not_configured_count],
  ] as const;
  return <section aria-label={t("Filtered network summary")} className="space-y-4">
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {cards.map(([label, value]) => <div key={label} className={`${panelClass} p-4`}><p className="text-xs font-medium text-slate-500">{t(label)}</p><p className="metric-value mt-3 text-teal-950">{t(value)}</p></div>)}
    </div>
    <div className="rounded-xl border border-teal-200 bg-teal-50 p-5 text-teal-950">
      <h2 className="flex items-center gap-2 text-sm font-semibold"><ChartNoAxesCombined size={18} aria-hidden="true" />{t("Modeled capacity subtotal · selected service")}</h2>
      <p className="mt-3 text-lg font-semibold" role="status" aria-live="polite">
        {t(summary.modeled_capacity_subtotal === null ? "Subtotal unavailable" : `${summary.modeled_capacity_subtotal.toLocaleString("en-GB")} modeled places`)}; {t(summary.known_estimate_count)}{t(" of ")}{t(summary.facility_count)}{t(" hospitals have known estimates; ")}{t(summary.unresolved_count)}{t(" unresolved")}</p>
      {summary.subtotal_status === "incompatible_profiles" && <p className="mt-2 text-sm">{t("Known estimates use different or missing requirement profiles. Their assumptions differ, so no subtotal is shown.")}</p>}
      {summary.subtotal_status === "no_known_estimates" && <p className="mt-2 text-sm">{t("There are no known estimates in this selection. Missing information is not zero.")}</p>}
      <p className="mt-3 flex items-start gap-2 text-xs leading-relaxed"><Building2 size={15} className="mt-0.5 shrink-0" aria-hidden="true" />{t("This subtotal covers known estimates in the filtered hospitals and assumes independent hospital resources. It is not a complete network total when reports are unresolved, and is not spare admission or transfer capacity. Do not add different services together.")}</p>
    </div>
  </section>;
}
