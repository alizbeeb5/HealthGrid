import type { FacilityCapacityResponse } from "../../lib/api/feature-2";

export type CapacityState =
  | { phase: "loading" | "updating" }
  | { phase: "ready"; data: FacilityCapacityResponse; source: "api" | "example" }
  | { phase: "error"; message: string };

/** Owns request ordering only; all modeled quantities come from API responses. */
export function createCapacityLoader(
  request: () => Promise<FacilityCapacityResponse>,
  publish: (state: CapacityState) => void,
) {
  let generation = 0;
  let started = false;
  return {
    async refresh() {
      const current = ++generation;
      publish({ phase: started ? "updating" : "loading" });
      started = true;
      try {
        const data = await request();
        if (current === generation) publish({ phase: "ready", data, source: "api" });
      } catch (error) {
        if (current === generation) publish({ phase: "error", message: error instanceof Error ? error.message : "Capacity could not be loaded. Try again." });
      }
    },
    showExample(data: FacilityCapacityResponse) {
      ++generation;
      started = true;
      publish({ phase: "ready", data, source: "example" });
    },
    cancel() { ++generation; },
  };
}
