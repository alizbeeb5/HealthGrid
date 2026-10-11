import type { Metadata } from "next";
import { headers } from "next/headers";
import { ExerciseProvider } from "../features/exercise/context";
import { WorkspaceShell } from "../features/exercise/navigation";
import "./globals.css";

export const metadata: Metadata = {
  title: "HealthGrid",
  description: "Health capacity, response and investment planning",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Request rendering keeps Next's inline scripts paired with the fresh CSP nonce.
  await headers();
  return (
    <html lang="en">
      <body>
        <ExerciseProvider>
          <a href="#main-content" className="sr-only focus:not-sr-only focus:block focus:bg-teal-900 focus:p-3 focus:text-white">Skip to content</a>
          <WorkspaceShell>{children}</WorkspaceShell>
        </ExerciseProvider>
      </body>
    </html>
  );
}
