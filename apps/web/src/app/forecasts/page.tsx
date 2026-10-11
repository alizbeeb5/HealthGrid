import { LocalizedText } from "@/lib/i18n/context";
import { Suspense } from "react";
import { ForecastDashboard } from "@/features/forecasting/forecast-dashboard";

export default function Page() {
  return <Suspense fallback={<p role="status"><LocalizedText>Loading forecasts…</LocalizedText></p>}><ForecastDashboard /></Suspense>;
}
