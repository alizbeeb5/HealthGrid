import Link from "next/link";
import { ArrowLeft, Database, MapPin } from "lucide-react";
import { facilityDataMode } from "../../lib/api/facilities";

export const buttonClass = "inline-flex items-center justify-center gap-2 rounded-lg bg-teal-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-900 disabled:cursor-wait disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700";
export const secondaryClass = "inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold hover:bg-slate-50 disabled:opacity-50";
export const panelClass = "rounded-xl border border-slate-200 bg-white shadow-sm";

export function Timestamp({ value }: { value: string | null }) {
  return value ? <time dateTime={value} title={value}>{new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium", timeStyle: "short",
  }).format(new Date(value))}</time> : <span>No report yet</span>;
}

export function Location({ latitude, longitude }: { latitude: number; longitude: number }) {
  return <span className="inline-flex items-center gap-1.5"><MapPin size={14} aria-hidden="true" />
    <span>Location: {latitude.toFixed(4)}°, {longitude.toFixed(4)}°</span>
  </span>;
}

export function ModeNotice() {
  return <div className="mb-7 flex items-start gap-3 rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-950">
    <Database size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
    <div><strong>{facilityDataMode === "demo" ? "Synthetic demo" : "Connected API"}</strong>
      <p className="mt-1">{facilityDataMode === "demo"
        ? "Example hospitals and reports. Updates stay in this browser. Freshness uses the displayed demo snapshot clock."
        : "Reports are loaded and saved through the hospital API. Demo hospitals use synthetic data."}</p>
    </div>
  </div>;
}

export function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    operating: "bg-emerald-50 text-emerald-800 ring-emerald-200", current: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    limited: "bg-amber-50 text-amber-900 ring-amber-200", stale: "bg-amber-50 text-amber-900 ring-amber-200",
    unavailable: "bg-rose-50 text-rose-800 ring-rose-200", unknown: "bg-slate-100 text-slate-600 ring-slate-200",
  };
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold capitalize ring-1 ring-inset ${colors[status] ?? colors.unknown}`}>{status}</span>;
}

export function BackLink() {
  return <Link href="/facilities" className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-teal-800 hover:underline"><ArrowLeft size={16} />All hospitals</Link>;
}

export function LoadingState({ detail = false }: { detail?: boolean }) {
  return <div role="status" aria-live="polite" className={`${panelClass} p-8`}>
    <p className="mb-6 text-sm text-slate-600">Loading {detail ? "hospital snapshot" : "hospitals"}…</p>
    <div aria-hidden="true" className="space-y-4 animate-pulse">
      {[1, 2, 3].map((item) => <div key={item} className="h-16 rounded-lg bg-slate-100" />)}
    </div>
  </div>;
}

export function LoadError({ message, retry }: { message: string; retry: () => void }) {
  return <div role="alert" className={`${panelClass} p-8`}>
    <h2 className="font-semibold">Could not load this view</h2><p className="my-3 text-sm text-slate-600">{message}</p>
    <button className={secondaryClass} onClick={retry}>Try again</button>
  </div>;
}

export function displayError(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Try loading again.";
}
