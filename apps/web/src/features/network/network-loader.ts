import type { NetworkMode, NetworkOverviewResponse, NetworkService, createNetworkClient } from "../../lib/api/network";
import { initialService } from "./presentation";

export type NetworkState =
  | { phase: "loading" | "updating" }
  | { phase: "error"; message: string }
  | { phase: "empty"; services: NetworkService[] }
  | { phase: "ready"; services: NetworkService[]; data: NetworkOverviewResponse; mode: NetworkMode };

/** One generation covers catalog + overview so service changes cannot race. */
export function createNetworkLoader(publish: (state: NetworkState) => void) {
  let generation = 0;
  let started = false;
  return {
    async refresh(client: ReturnType<typeof createNetworkClient>, mode: NetworkMode, requested: string | null) {
      const current = ++generation;
      publish({ phase: started ? "updating" : "loading" });
      started = true;
      try {
        const { items } = await client.listServices();
        if (current !== generation) return;
        if (!items.length) { publish({ phase: "empty", services: items }); return; }
        const serviceId = initialService(items, requested)!;
        const data = await client.getOverview(serviceId);
        if (data.service_id !== serviceId) throw new Error("The network response does not match the selected service. Refresh to try again.");
        if (current === generation) publish({ phase: "ready", services: items, data, mode });
      } catch (error) {
        if (current === generation) publish({ phase: "error", message: error instanceof Error ? error.message : "Network reports could not be loaded." });
      }
    },
    cancel() { ++generation; },
  };
}
