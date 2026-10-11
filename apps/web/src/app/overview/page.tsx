import { LocalizedText } from "@/lib/i18n/context";
import { Suspense } from "react";
import { NetworkDashboard } from "@/features/network/network-dashboard";

export default function Page() {
  return <Suspense fallback={<p role="status"><LocalizedText>Loading network overview…</LocalizedText></p>}><NetworkDashboard /></Suspense>;
}
