"use client";
import { useI18n } from "@/lib/i18n/context";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { useExercise } from "./context";
import { secondaryClass } from "../facilities/shared";

export function NextStep({ to, children }: { to: string; children: React.ReactNode }) {
  const { t } = useI18n();
  const exercise = useExercise();
  return <div className="flex justify-end border-t border-slate-200 pt-5"><Link className={secondaryClass} href={exercise?.links?.[to] ?? `/${to}`}>{t(children)}<ArrowRight size={16} /></Link></div>;
}
export function useSavedResource<T>(load: () => Promise<T>, identity: string) {
  const [data, setData] = useState<T>(); const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true); const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true; setLoading(true); setData(undefined); setError(undefined);
    void load().then((result) => { if (active) setData(result); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Could not load this step."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
    // identity represents the immutable API resource; retries are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity, attempt]);
  return { data, error, loading, retry: () => setAttempt((value) => value + 1) };
}
export function savedId(link: string | undefined, key: string) {
  return new URLSearchParams(link?.split("?")[1]).get(key) ?? "";
}
