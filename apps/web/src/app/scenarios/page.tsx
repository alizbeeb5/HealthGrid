import { LocalizedText } from "@/lib/i18n/context";
import { ExerciseRoute } from "@/features/exercise/route";
import { Suspense } from "react";
import { IncidentDashboard } from "@/features/scenarios/incident-dashboard";

export default function Page() {
  return <Suspense fallback={<p role="status"><LocalizedText>Loading incident workspace…</LocalizedText></p>}><ExerciseRoute screen="incident"><IncidentDashboard /></ExerciseRoute></Suspense>;
}
