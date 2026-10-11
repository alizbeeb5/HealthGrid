"use client";
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { Languages } from "lucide-react";
import { localeTag, translateValue, type Locale } from "./translate";

type I18n = { locale: Locale; setLocale: (locale: Locale) => void; t: <T>(value: T) => T };
const Context = createContext<I18n>({ locale: "en", setLocale: () => {}, t: <T,>(value: T) => value });

export function LanguageProvider({ initialLocale, children }: { initialLocale: Locale; children: React.ReactNode }) {
  const [locale, updateLocale] = useState(initialLocale);
  const setLocale = useCallback((next: Locale) => {
    updateLocale(next);
    document.documentElement.lang = next;
    document.documentElement.dir = next === "ar" ? "rtl" : "ltr";
    document.cookie = `healthgrid_locale=${next}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
  }, []);
  const value = useMemo<I18n>(() => ({ locale, setLocale, t: <T,>(input: T) => translateValue(input, locale) }), [locale, setLocale]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useI18n() {
  const value = useContext(Context);
  return { ...value, formatLocale: localeTag(value.locale) };
}
export function LanguageSwitch() {
  const { locale, setLocale } = useI18n();
  return <button type="button" onClick={() => setLocale(locale === "en" ? "ar" : "en")}
    className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-teal-900 hover:bg-teal-50"
    lang={locale === "en" ? "ar" : "en"} aria-label={locale === "en" ? "Switch to Arabic / التبديل إلى العربية" : "التبديل إلى الإنجليزية / Switch to English"}>
    <Languages size={16} aria-hidden="true" />{locale === "en" ? "العربية" : "English"}
  </button>;
}
export function LocalizedText({ children }: { children: string }) {
  const { t } = useI18n();
  return <>{t(children)}</>;
}
