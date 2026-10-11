import { LocalizedText } from "@/lib/i18n/context";
import { ExerciseRoute } from "@/features/exercise/route";
import { Suspense } from "react";
import { DecisionDashboard } from "@/features/decisions/decision-dashboard";
export default function Page() {
  return <Suspense fallback={<p role="status"><LocalizedText>Loading decision board…</LocalizedText></p>}><ExerciseRoute screen="outcomes"><DecisionDashboard /></ExerciseRoute></Suspense>;
}
