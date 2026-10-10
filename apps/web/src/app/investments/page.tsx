import { Suspense } from "react";
import { InvestmentDashboard } from "@/features/investments/investment-dashboard";
export default function Page() {
  return <Suspense fallback={<p role="status">Loading funding workspace…</p>}><InvestmentDashboard /></Suspense>;
}
