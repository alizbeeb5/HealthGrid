"use client";
import Link from "next/link";
import { SignOutButton } from "../../components/sign-out-button";
import { usePathname } from "next/navigation";
import { Activity, ArrowRight, CheckCircle2, LayoutDashboard, Building2, TrendingUp, Siren, ArrowLeftRight, Wallet, ClipboardCheck } from "lucide-react";
import { useRef, useState } from "react";
import { buttonClass } from "../facilities/shared";
import { useExercise } from "./context";

const pages = [
  { key: "overview", label: "Dashboard", icon: LayoutDashboard, group: "Monitor" },
  { key: "facilities", label: "Hospitals", icon: Building2, group: "Monitor" },
  { key: "forecasts", label: "Forecasts", icon: TrendingUp, group: "Monitor" },
  { key: "scenarios", label: "Incident & AI", icon: Siren, group: "Plan & act" },
  { key: "allocation", label: "Response plan", icon: ArrowLeftRight, group: "Plan & act" },
  { key: "investments", label: "Recovery funding", icon: Wallet, group: "Plan & act" },
  { key: "decisions", label: "Outcomes", icon: ClipboardCheck, group: "Plan & act" },
] as const;

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const path = usePathname(); const exercise = useExercise();
  const active = pages.find((page) => path.startsWith(`/${page.key}`));
  const phase = exercise?.phase === "assessment" ? "Assessment" : exercise?.phase === "response" ? "Response" : "Recovery";
  const clock = exercise?.clock ? new Date(exercise.clock).toLocaleString("en-GB", { timeZone: "Asia/Beirut", dateStyle: "medium", timeStyle: "short" }) : undefined;
  const href = (key: string) => exercise?.enabled ? exercise.links?.[key] ?? `/${key}` : `/${key}`;
  if (path === "/login") return <main id="main-content">{children}</main>;
  return <div className="min-h-screen lg:pl-52">
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-52 flex-col border-r border-slate-200 bg-white lg:flex">
      <Link href="/overview" className="flex items-center gap-2.5 px-5 py-6 text-lg font-bold"><span className="rounded-lg bg-teal-900 p-2 text-white"><Activity size={20} aria-hidden="true" /></span>HealthGrid</Link>
      <nav aria-label="Main navigation" className="flex-1 overflow-y-auto px-3 pb-6">{["Monitor", "Plan & act"].map((group) => <div key={group} className="mb-6"><p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-widest text-slate-400">{group}</p><ul className="space-y-1">{pages.filter((page) => page.group === group).map(({ key, label, icon: Icon }) => <li key={key}><Link href={href(key)} aria-current={active?.key === key ? "page" : undefined} className={`flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium ${active?.key === key ? "bg-teal-50 text-teal-900" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}><Icon size={18} aria-hidden="true" />{label}</Link></li>)}</ul></div>)}</nav>
      {exercise?.enabled && <div className="border-t border-slate-100 px-5 py-4"><p className="text-xs font-semibold text-slate-700">Beirut exercise</p><p className="mt-1 text-[11px] text-slate-500">Synthetic operational data</p></div>}
    </aside>
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
      <div className="mx-auto flex min-h-14 max-w-[1440px] flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-2 sm:px-6">
        <div className="flex items-center gap-3"><Link href="/overview" className="font-bold text-teal-900 lg:hidden">HealthGrid</Link><p className="hidden text-xs text-slate-500 sm:block">{exercise?.enabled ? "Beirut response" : "Health system coordination"}<span className="mx-2 text-slate-300">/</span><span className="font-medium text-slate-700">{active?.label ?? "Workspace"}</span></p></div>
        <div className="flex items-center gap-4"><SignOutButton />
        {exercise?.enabled && <div className="flex items-center gap-3 text-xs text-slate-500"><span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">{phase}</span><time dateTime={exercise.clock ?? undefined} title="Exercise clock · Beirut time">{clock}</time></div>}</div>
      </div>
      <nav aria-label="Mobile navigation" className="flex gap-1 overflow-x-auto border-t border-slate-100 px-3 lg:hidden">{pages.map(({ key, label }) => <Link key={key} href={href(key)} aria-current={active?.key === key ? "page" : undefined} className={`whitespace-nowrap border-b-2 px-3 py-3 text-xs font-semibold ${active?.key === key ? "border-teal-700 text-teal-900" : "border-transparent text-slate-500"}`}>{label}</Link>)}</nav>
      {exercise?.enabled && <p className="px-4 pb-2 text-[10px] text-slate-500 lg:hidden">Beirut exercise · Synthetic operational data</p>}
    </header>
    <main id="main-content" className="mx-auto max-w-[1440px] px-4 py-5 sm:px-6 lg:py-6">{children}</main>
  </div>;
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
    {phase === "recovery" ? <p className="flex items-center gap-2 font-semibold text-teal-950"><CheckCircle2 size={19} />Recovery reports received.</p> : <><h2 className="font-semibold text-teal-950">{phase === "assessment" ? "Record the response" : "Verify recovery"}</h2><p className="mt-2 text-sm leading-6 text-teal-900">{phase === "assessment" ? "Simulate the transfer, then receive follow-up reports." : "Advance to 11 August and compare fresh reports with the recovery target."}</p><button disabled={pending} onClick={advance} className={`${buttonClass} mt-4`}>{pending ? "Saving…" : phase === "assessment" ? "Simulate transfer and receive reports" : "Simulate recovery and review outcomes"}<ArrowRight size={15} /></button><p className="mt-3 text-xs text-teal-800">Simulation only · records demo actions and report arrivals.</p></>}
    {error && <p role="alert" className="mt-3 text-sm text-rose-800">{error}</p>}
  </section>;
}
