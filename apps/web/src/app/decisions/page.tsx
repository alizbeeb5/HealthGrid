import { Suspense } from "react";
import { DecisionDashboard } from "@/features/decisions/decision-dashboard";
export default function Page() {
  return <Suspense fallback={<p role="status">Loading decision board…</p>}><DecisionDashboard /></Suspense>;
}
