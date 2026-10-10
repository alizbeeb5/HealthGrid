"use client";
import { useSearchParams } from "next/navigation";
import { savedId } from "./journey";
import { useExercise } from "./context";
import { BeirutIncident } from "./incident";
import { BeirutFunding } from "./funding";
import { BeirutOutcomes } from "./outcomes";

export function ExerciseRoute({ screen, children }: { screen: "incident" | "funding" | "outcomes"; children: React.ReactNode }) {
  const exercise = useExercise(); const params = useSearchParams();
  const differentIncident = screen === "incident" && params.has("run_id") && params.get("run_id") !== savedId(exercise?.links?.scenarios, "run_id");
  const differentAllocation = screen === "funding" && params.has("allocation_run_id") && params.get("allocation_run_id") !== exercise?.investment_input?.allocation_run_id;
  if (!exercise?.enabled || params.get("advanced") === "1" || differentIncident || differentAllocation || (screen === "outcomes" && params.has("source_run_id"))) return children;
  return screen === "incident" ? <BeirutIncident /> : screen === "funding" ? <BeirutFunding /> : <BeirutOutcomes />;
}
