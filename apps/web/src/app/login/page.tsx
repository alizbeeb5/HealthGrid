"use client";
import { useState, type FormEvent } from "react";
import { Activity, ArrowRight, Eye, EyeOff, LockKeyhole } from "lucide-react";

export default function SignInPage() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const form = new FormData(event.currentTarget);
    setPending(true); setError("");
    try {
      const response = await fetch("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: form.get("username"), password: form.get("password"), returnTo: new URLSearchParams(window.location.search).get("returnTo") }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? "Could not sign in. Try again.");
      window.location.assign(body.redirect);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not connect. Try again."); setPending(false); }
  }
  return <div className="flex min-h-screen items-center justify-center bg-slate-50 px-5 py-12">
    <div className="w-full max-w-md">
      <div className="mb-8 flex items-center justify-center gap-3 text-2xl font-bold text-slate-900"><span className="rounded-xl bg-teal-900 p-3 text-white"><Activity size={26} aria-hidden="true" /></span>HealthGrid</div>
      <section className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm sm:p-10" aria-labelledby="signin-title">
        <div className="mb-5 inline-flex rounded-full bg-teal-50 p-3 text-teal-800"><LockKeyhole size={22} aria-hidden="true" /></div>
        <h1 id="signin-title" className="text-2xl font-bold text-slate-900">Sign in</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">Access your hospital planning workspace.</p>
        <form onSubmit={signIn} className="mt-7 space-y-5">
          <div><label htmlFor="username" className="mb-2 block text-sm font-medium text-slate-700">Username</label><input id="username" name="username" autoComplete="username" defaultValue="healthgrid" required maxLength={128} className="w-full rounded-lg border border-slate-300 px-3 py-3 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100" /></div>
          <div><label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-700">Password</label><div className="relative"><input id="password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required maxLength={256} aria-describedby={error ? "signin-error" : undefined} className="w-full rounded-lg border border-slate-300 px-3 py-3 pr-12 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100" /><button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} className="absolute inset-y-0 right-0 px-3 text-slate-500">{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></div>
          {error && <p id="signin-error" role="alert" className="rounded-lg bg-rose-50 px-3 py-3 text-sm text-rose-800">{error}</p>}
          <button disabled={pending} className="flex w-full items-center justify-center gap-2 rounded-lg bg-teal-900 px-4 py-3 font-semibold text-white hover:bg-teal-800 disabled:opacity-60">{pending ? "Signing in…" : "Sign in"}<ArrowRight size={17} aria-hidden="true" /></button>
        </form>
      </section>
      <p className="mt-6 text-center text-xs text-slate-500">Health system coordination · HealthGrid</p>
    </div>
  </div>;
}
