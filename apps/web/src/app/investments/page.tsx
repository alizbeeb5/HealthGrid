import { LocalizedText } from "@/lib/i18n/context";
import { ExerciseRoute } from "@/features/exercise/route";
import { Suspense } from "react";
import { InvestmentDashboard } from "@/features/investments/investment-dashboard";
export default function Page() {
  return <Suspense fallback={<p role="status"><LocalizedText>Loading funding workspace…</LocalizedText></p>}><ExerciseRoute screen="funding"><InvestmentDashboard /></ExerciseRoute></Suspense>;
}
