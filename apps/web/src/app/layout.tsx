import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "HealthGrid",
  description: "Health capacity, response and investment planning",
};

const pages = ["overview", "facilities", "forecasts", "scenarios", "investments", "decisions"];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-slate-200 bg-white px-6 py-5">
          <Link href="/overview" className="text-xl font-bold">HealthGrid</Link>
          <nav aria-label="Main navigation" className="mt-4 flex flex-wrap gap-5">
            {pages.map((page) => (
              <Link key={page} href={`/${page}`} className="capitalize hover:underline">{page}</Link>
            ))}
          </nav>
        </header>
        <main className="mx-auto max-w-6xl p-6 md:p-10">{children}</main>
      </body>
    </html>
  );
}
