"use client";
import { useI18n } from "@/lib/i18n/context";
export function PagePlaceholder({ title, description }: { title: string; description: string }) {
  const { t } = useI18n();
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-8">
      <p className="mb-3 text-sm font-medium text-slate-500">{t("Development scaffold")}</p>
      <h1 className="text-3xl font-semibold">{t(title)}</h1>
      <p className="mt-4 max-w-2xl leading-7 text-slate-600">{t(description)}</p>
      <p className="mt-6 text-sm text-slate-500">{t("This screen is not connected to operational data yet.")}</p>
    </section>
  );
}
