import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { ExerciseProvider } from "../features/exercise/context";
import { WorkspaceShell } from "../features/exercise/navigation";
import { LanguageProvider, LocalizedText } from "../lib/i18n/context";
import "./globals.css";

export const metadata: Metadata = {
  title: "HealthGrid",
  description: "Health capacity, response and investment planning",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Request rendering keeps Next's inline scripts paired with the fresh CSP nonce.
  await headers();
  const locale = (await cookies()).get("healthgrid_locale")?.value === "ar" ? "ar" : "en";
  return (
    <html lang={locale} dir={locale === "ar" ? "rtl" : "ltr"}>
      <body>
        <LanguageProvider initialLocale={locale}>
        <ExerciseProvider>
          <a href="#main-content" className="sr-only focus:not-sr-only focus:block focus:bg-teal-900 focus:p-3 focus:text-white"><LocalizedText>Skip to content</LocalizedText></a>
          <WorkspaceShell>{children}</WorkspaceShell>
        </ExerciseProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
