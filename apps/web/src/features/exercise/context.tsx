"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { configureExerciseMode } from "../../lib/api/facilities";
import type { components } from "../../lib/api/schema";

type Exercise = components["schemas"]["ExerciseContext"];
const Context = createContext<Exercise | null>(null);
export function ExerciseProvider({ children }: { children: React.ReactNode }) {
  const [exercise, setExercise] = useState<Exercise | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let mounted = true;
    const timeout = setTimeout(() => controller.abort(), 5000);
    void fetch("/api/v1/demo", { cache: "no-store", signal: controller.signal }).then(async (response) => {
      if (!response.ok) return;
      const next = await response.json() as Exercise;
      if (mounted) { configureExerciseMode(next.enabled); setExercise(next); }
    }).catch(() => { /* Ordinary pages retain their own connection error states. */ })
      .finally(() => { clearTimeout(timeout); if (mounted) setReady(true); });
    return () => { mounted = false; clearTimeout(timeout); controller.abort(); };
  }, []);
  if (!ready) return <p role="status" className="mx-auto max-w-7xl p-8 text-sm text-slate-600">Connecting to the planning workspace…</p>;
  return <Context.Provider value={exercise}>{children}</Context.Provider>;
}
export const useExercise = () => useContext(Context);
export function useExerciseNames() {
  const exercise = useExercise();
  return {
    hospital: (id: string) => exercise?.hospitals?.find((h) => h.facility_id === id)?.name.replace(" — fictional", "") ?? id,
    resource: (id: string) => exercise?.resources?.find((r) => r.resource_id === id)?.name ?? id.replaceAll("-", " "),
  };
}
