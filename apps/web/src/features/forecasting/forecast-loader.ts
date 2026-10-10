import type { ForecastPreview } from "./demo-client";

export type ForecastState =
  | { phase: "loading" | "updating" }
  | { phase: "error"; message: string }
  | { phase: "ready"; data: ForecastPreview };

/** Source injection isolates presentation from the generated API adapter. */
export function createForecastLoader(
  request: (facilityId: string, serviceId: string) => Promise<ForecastPreview>,
  publish: (state: ForecastState) => void,
) {
  let generation = 0;
  let started = false;
  return {
    async refresh(facilityId: string, serviceId: string) {
      const current = ++generation;
      publish({ phase: started ? "updating" : "loading" });
      started = true;
      try {
        const data = await request(facilityId, serviceId);
        if (data.facility_id !== facilityId || data.service_id !== serviceId) throw new Error("The forecast does not match the selected hospital and service. Refresh to try again.");
        if (current === generation) publish({ phase: "ready", data });
      } catch (error) {
        if (current === generation) publish({ phase: "error", message: error instanceof Error ? error.message : "The forecast could not be loaded. Try again." });
      }
    },
    cancel() { ++generation; },
  };
}
