import examples from "./network-fixtures.generated.json";
import { facilityRequest } from "./facilities";
import { FacilityClientError } from "./facilities-error";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type NetworkOverviewResponse = Schemas["NetworkOverviewResponse"];
export type NetworkFacilityResult = Schemas["NetworkFacilityResult"];
export type NetworkServiceListResponse = Schemas["NetworkServiceListResponse"];
export type NetworkService = Schemas["NetworkService"];
export type NetworkMode = "api" | "example";

async function networkRequest<T>(path: string): Promise<T> {
  try { return await facilityRequest<T>(path); }
  catch (error) {
    if (error instanceof FacilityClientError && error.status === 404) {
      throw new FacilityClientError("Network reports could not be loaded. Try again.", 404);
    }
    throw error;
  }
}

/** Uses the agreed network endpoints; request failures never substitute fixtures. */
export function createNetworkClient(mode: NetworkMode) {
  return {
    async listServices(): Promise<NetworkServiceListResponse> {
      return mode === "example" ? structuredClone(examples.services) as NetworkServiceListResponse
        : networkRequest("/api/v1/network/services");
    },
    async getOverview(serviceId: string): Promise<NetworkOverviewResponse> {
      if (mode === "example") {
        return serviceId === examples.overview.service_id
          ? structuredClone(examples.overview) as NetworkOverviewResponse
          : { ...structuredClone(examples.unknownService), service_id: serviceId } as NetworkOverviewResponse;
      }
      return networkRequest(`/api/v1/network/overview?${new URLSearchParams({ service_id: serviceId })}`);
    },
  };
}
