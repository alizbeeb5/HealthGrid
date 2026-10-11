"use client";
import { useI18n } from "@/lib/i18n/context";
import type { ReactNode } from "react";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  const { t } = useI18n();
  return <header className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-2xl font-semibold tracking-tight text-slate-900">{t(title)}</h1>{description && <p className="mt-1 text-sm text-slate-500">{t(description)}</p>}</div>{actions && <div className="flex flex-wrap items-center gap-2">{t(actions)}</div>}</header>;
}
