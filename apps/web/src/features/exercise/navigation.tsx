"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, ArrowRight, CheckCircle2 } from "lucide-react";
import { useRef, useState } from "react";
import { buttonClass } from "../facilities/shared";
import { useExercise } from "./context";

const pages = [
  ["overview", "Situation"], ["forecasts", "Forecast"], ["scenarios", "Incident & AI"],
  ["allocation", "Response"], ["investments", "Recovery funding"], ["decisions", "Outcomes"],
] as const;
export function Navigation() {
  const path = usePathname(); const exercise = useExercise();
  return <header className="border-b border-slate-200 bg-white">
    <div className="mx-auto max-w-7xl px-5 pt-5 sm:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3"><Link href="/overview" className="flex items-center gap-3 text-xl font-bold tracking-tight"><span className="rounded-xl bg-teal-900 p-2 text-white"><Activity size={23} aria-hidden="true" /></span>HealthGrid<span className="hidden text-sm font-normal text-slate-500 sm:inline">/ Beirut response</span></Link><Link href="/facilities" className="text-sm font-medium text-teal-800 hover:underline">Hospital reports ↗</Link></div>
      <nav aria-label="Planning workflow" className="mt-5 flex gap-1 overflow-x-auto pb-1">{pages.map(([key, label], i) => <Link key={key} href={exercise?.enabled ? exercise.links?.[key] ?? `/${key}` : `/${key}`} aria-current={path.startsWith(`/${key}`) ? "page" : undefined} className={`whitespace-nowrap rounded-t-lg border-b-2 px-3 py-3 text-sm font-semibold ${path.startsWith(`/${key}`) ? "border-teal-700 bg-teal-50 text-teal-900" : "border-transparent text-slate-500 hover:bg-slate-50"}`}><span className="mr-2 text-xs opacity-60">{i + 1}</span>{label}</Link>)}</nav>
    </div>
  </header>;
}
export function ExerciseBanner() {
  const exercise = useExercise();
  if (!exercise?.enabled) return null;
  return <div className="border-b border-slate-200 bg-slate-50 px-5 py-2 sm:px-8"><div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 text-xs text-slate-500"><p><span className="font-semibold text-slate-700">Beirut explosion exercise</span> · Synthetic hospitals and operational data</p><p>{exercise.phase === "assessment" ? "Incident assessment" : exercise.phase === "response" ? "Transfer reported" : "Recovery reports received"} · {exercise.clock && new Date(exercise.clock).toLocaleString("en-GB", { timeZone: "Asia/Beirut", dateStyle: "medium", timeStyle: "short" })} Beirut time</p></div></div>;
}
export function ExerciseAdvance() {
  const exercise = useExercise(); const lock = useRef(false);
  const [pending, setPending] = useState(false); const [error, setError] = useState<string>();
  if (!exercise?.enabled) return null;
  const phase = exercise.phase;
  async function advance() {
    if (!exercise || lock.current || phase === "recovery") return;
    lock.current = true; setPending(true); setError(undefined);
    try {
      const response = await fetch("/api/v1/demo/advance", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_phase: phase, target_phase: phase === "assessment" ? "response" : "recovery" }) });
      if (!response.ok) { const body = await response.json(); throw new Error(body.error?.message ?? body.detail ?? "Could not complete the exercise step. Refresh before retrying."); }
      window.location.assign("/decisions");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not confirm this step."); lock.current = false; setPending(false); }
  }
  return <section className="rounded-xl border border-teal-200 bg-teal-50 p-5">
    {phase === "recovery" ? <p className="flex items-center gap-2 font-semibold text-teal-950"><CheckCircle2 size={19} />Recovery reports are ready to compare below.</p> : <><h2 className="font-semibold text-teal-950">{phase === "assessment" ? "Next: record the immediate response" : "Next: verify the recovery package"}</h2><p className="mt-2 text-sm leading-6 text-teal-900">{phase === "assessment" ? "Rehearse the reviewed transfer and receive updated hospital reports." : "Advance to 11 August, rehearse the recovery work, and compare evidence before and after fresh reports arrive."}</p><button disabled={pending} onClick={advance} className={`${buttonClass} mt-4`}>{pending ? "Saving…" : phase === "assessment" ? "Simulate transfer and receive reports" : "Simulate recovery and review outcomes"}<ArrowRight size={15} /></button><p className="mt-3 text-xs text-teal-800">Demo action: records simulated approval, completion and separate report arrivals for the original plan. No real dispatch or spending.</p></>}
    {error && <p role="alert" className="mt-3 text-sm text-rose-800">{error}</p>}
  </section>;
}
