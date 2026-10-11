"use client";
import { LanguageSwitch, useI18n } from "@/lib/i18n/context";

import { signInRequest } from "./sign-in";
import { useRef, useState, type FormEvent } from "react";
import { Activity, ArrowRight, Eye, EyeOff, LockKeyhole } from "lucide-react";

export function SignInForm({ initialUsername }: { initialUsername: string }) {
  const { t } = useI18n();
  const lock = useRef(false);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current) return;
    const form = new FormData(event.currentTarget);
    lock.current = true;
    setPending(true); setError("");
    try {
      const destination = await signInRequest(String(form.get("username") ?? ""), String(form.get("password") ?? ""), new URLSearchParams(window.location.search).get("returnTo"));
      window.location.replace(destination);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not connect. Try again.");
      lock.current = false; setPending(false);
      requestAnimationFrame(() => errorRef.current?.focus());
    }
  }
  return <div className="flex min-h-screen items-center justify-center bg-slate-50 px-5 py-12">
    <div className="w-full max-w-md">
      <div className="mb-5 flex justify-end"><LanguageSwitch /></div>
      <div className="mb-8 flex items-center justify-center gap-3 text-2xl font-bold text-slate-900"><span className="rounded-xl bg-teal-900 p-3 text-white"><Activity size={26} aria-hidden="true" /></span>{t("HealthGrid")}</div>
      <section className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm sm:p-10" aria-labelledby="signin-title">
        <div className="mb-5 inline-flex rounded-full bg-teal-50 p-3 text-teal-800"><LockKeyhole size={22} aria-hidden="true" /></div>
        <h1 id="signin-title" className="text-2xl font-bold text-slate-900">{t("Sign in")}</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">{t("Access your hospital planning workspace.")}</p>
        <form onSubmit={signIn} aria-busy={pending} className="mt-7 space-y-5">
          <fieldset disabled={pending} className="space-y-5">
          <div><label htmlFor="username" className="mb-2 block text-sm font-medium text-slate-700">{t("Username")}</label><input id="username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} dir="ltr" autoFocus defaultValue={initialUsername} required maxLength={128} className="w-full rounded-lg border border-slate-300 px-3 py-3 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100" /></div>
          <div><label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-700">{t("Password")}</label><div className="relative"><input id="password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" dir="ltr" required maxLength={256} aria-invalid={Boolean(error)} aria-describedby={error ? "signin-error" : undefined} className="w-full rounded-lg border border-slate-300 px-12 py-3 text-sm outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100" /><button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={t(showPassword ? "Hide password" : "Show password")} aria-pressed={showPassword} className="absolute inset-y-0 end-0 px-3 text-slate-500">{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div></div>
          {error && <p ref={errorRef} tabIndex={-1} id="signin-error" role="alert" className="rounded-lg bg-rose-50 px-3 py-3 text-sm text-rose-800">{t(error)}</p>}
          <button type="submit" disabled={pending} className="flex w-full items-center justify-center gap-2 rounded-lg bg-teal-900 px-4 py-3 font-semibold text-white hover:bg-teal-800 disabled:opacity-60">{t(pending ? "Signing in…" : "Sign in")}<ArrowRight size={17} aria-hidden="true" /></button>
          </fieldset>
        </form>
      </section>
      <p className="mt-6 text-center text-xs text-slate-500">{t("Health system coordination · HealthGrid")}</p>
    </div>
  </div>;
}
