import examples from "./capacity-fixtures.generated.json";
import { facilityRequest } from "./facilities";
import { FacilityClientError } from "./facilities-error";
import type { FacilityCapacityResponse } from "./feature-2";

const responses = examples.responses as Record<string, FacilityCapacityResponse>;

export async function getFacilityCapacity(facility_id: string): Promise<FacilityCapacityResponse> {
  try {
    return await facilityRequest(`/api/v1/capacity/facilities/${encodeURIComponent(facility_id)}`);
  } catch (error) {
    if (error instanceof FacilityClientError && error.status === 404 && error.detail?.code !== "facility_not_found") {
      throw new FacilityClientError("Capacity could not be loaded. Try again.", 404);
    }
    throw error;
  }
}

export function hasCapacityExample(facility_id: string): boolean {
  return Object.hasOwn(responses, facility_id);
}

export function getCapacityExample(facility_id: string): FacilityCapacityResponse {
  if (!hasCapacityExample(facility_id)) throw new FacilityClientError("No synthetic capacity example exists for this hospital.");
  return structuredClone(responses[facility_id]);
}
