"use client";
import { useI18n } from "@/lib/i18n/context";

import { useState } from "react";
import { endSession } from "../lib/auth/sign-out";

export function SignOutButton() {
  const { t } = useI18n();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function signOut() {
    if (pending) return;
    setPending(true); setError("");
    try {
      await endSession();
      // Full navigation discards the cached workspace and replaces its history entry.
      window.location.replace("/login");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not sign out. Please try again.");
      setPending(false);
    }
  }
  return <div className="text-end">
    <button type="button" onClick={signOut} disabled={pending} className="rounded-lg px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-60">{t(pending ? "Signing out…" : "Sign out")}</button>
    {error && <p role="alert" className="max-w-56 text-xs text-rose-800">{t(error)}</p>}
  </div>;
}
