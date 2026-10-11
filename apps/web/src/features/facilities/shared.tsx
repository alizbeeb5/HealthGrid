"use client";
import { useI18n } from "@/lib/i18n/context";
import { useExercise } from "../exercise/context";
import Link from "next/link";
import { ArrowLeft, Database, MapPin } from "lucide-react";
import { facilityDataMode } from "../../lib/api/facilities";

export const buttonClass = "inline-flex items-center justify-center gap-2 rounded-lg bg-teal-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-900 disabled:cursor-wait disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700";
export const secondaryClass = "inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold hover:bg-slate-50 disabled:opacity-50";
export const panelClass = "rounded-xl border border-slate-200 bg-white shadow-sm";

export function Timestamp({ value }: { value: string | null }) {
  const { t, locale } = useI18n();
  return value ? <time dateTime={value} title={t(value)}>{t(new Intl.DateTimeFormat(locale === "ar" ? "ar-LB-u-nu-latn" : "en-GB", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Beirut",
  }).format(new Date(value)))}</time> : <span>{t("No report yet")}</span>;
}

export function Location({ latitude, longitude }: { latitude: number; longitude: number }) {
  const { t, locale } = useI18n();
  return <span className="inline-flex items-center gap-1.5"><MapPin size={14} aria-hidden="true" />
    <span>{t("Location: ")}{t(latitude.toFixed(4))}°, {t(longitude.toFixed(4))}°</span>
  </span>;
}

export function ModeNotice() {
  const { t, locale } = useI18n();
  const exercise = useExercise();
  if (exercise?.enabled || facilityDataMode !== "demo") return null;
  return <div className="mb-7 flex items-start gap-3 rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-950">
    <Database size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
    <div><strong>{t("Synthetic demo")}</strong>
      <p className="mt-1">{t("Example hospitals and reports. Updates stay in this browser. Freshness uses the displayed demo snapshot clock.")}</p>
    </div>
  </div>;
}

export function StatusBadge({ status }: { status: string }) {
  const { t, locale } = useI18n();
  const colors: Record<string, string> = {
    operating: "bg-emerald-50 text-emerald-800 ring-emerald-200", current: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    limited: "bg-amber-50 text-amber-900 ring-amber-200", stale: "bg-amber-50 text-amber-900 ring-amber-200",
    unavailable: "bg-rose-50 text-rose-800 ring-rose-200", unknown: "bg-slate-100 text-slate-600 ring-slate-200",
  };
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold capitalize ring-1 ring-inset ${colors[status] ?? colors.unknown}`}>{t(status)}</span>;
}

export function BackLink({ returnTo }: { returnTo?: string } = {}) {
  const { t, locale } = useI18n();
  return <Link href={returnTo ?? "/facilities"} className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-teal-800 hover:underline"><ArrowLeft size={16} />{t(returnTo ? "Back to network overview" : "All hospitals")}</Link>;
}

export function LoadingState({ detail = false }: { detail?: boolean }) {
  const { t, locale } = useI18n();
  return <div role="status" aria-live="polite" className={`${panelClass} p-8`}>
    <p className="mb-6 text-sm text-slate-600">{t("Loading ")}{t(detail ? "hospital snapshot" : "hospitals")}…</p>
    <div aria-hidden="true" className="space-y-4 animate-pulse">
      {[1, 2, 3].map((item) => <div key={item} className="h-16 rounded-lg bg-slate-100" />)}
    </div>
  </div>;
}

export function LoadError({ message, retry }: { message: string; retry: () => void }) {
  const { t, locale } = useI18n();
  return <div role="alert" className={`${panelClass} p-8`}>
    <h2 className="font-semibold">{t("Could not load this view")}</h2><p className="my-3 text-sm text-slate-600">{t(message)}</p>
    <button className={secondaryClass} onClick={retry}>{t("Try again")}</button>
  </div>;
}

export function displayError(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Try loading again.";
}
