import { Suspense } from "react";
import { NetworkDashboard } from "@/features/network/network-dashboard";

export default function Page() {
  return <Suspense fallback={<p role="status">Loading network overview…</p>}><NetworkDashboard /></Suspense>;
}
