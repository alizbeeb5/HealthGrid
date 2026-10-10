import { ExerciseRoute } from "@/features/exercise/route";
import { Suspense } from "react";
import { IncidentDashboard } from "@/features/scenarios/incident-dashboard";

export default function Page() {
  return <Suspense fallback={<p role="status">Loading incident workspace…</p>}><ExerciseRoute screen="incident"><IncidentDashboard /></ExerciseRoute></Suspense>;
}
