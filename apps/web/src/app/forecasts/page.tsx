import { Suspense } from "react";
import { ForecastDashboard } from "@/features/forecasting/forecast-dashboard";

export default function Page() {
  return <Suspense fallback={<p role="status">Loading forecasts…</p>}><ForecastDashboard /></Suspense>;
}
