import type { ErrorResponse, FacilityListResponse, FacilitySnapshotResponse, ObservationCreate, ObservationResponse } from "./feature-1";
import { createDemoClient } from "./facilities-demo";
import { FacilityClientError } from "./facilities-error";

export { FacilityClientError } from "./facilities-error";
export const facilityDataMode = process.env.NEXT_PUBLIC_FACILITIES_DATA_MODE === "demo" ? "demo" : "api";

/** Same-origin requests use the existing Next.js server proxy. Never retry POST. */
export async function facilityRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(path, { ...init, cache: "no-store" }); }
  catch {
    throw new FacilityClientError(init?.method === "POST"
      ? "The save could not be confirmed. Refresh the snapshot to check before submitting again."
      : "Could not connect to the API. Try loading again.");
  }
  if (!response.ok) {
    let detail: ErrorResponse["error"] | undefined;
    try {
      const body = await response.json();
      if (body.error && typeof body.error.message === "string" && Array.isArray(body.error.fields)
        && body.error.fields.every((field: { field?: unknown; message?: unknown }) => typeof field?.field === "string" && typeof field?.message === "string")) {
        detail = body.error;
      }
    } catch { /* A proxy may return HTML instead of a contract error. */ }
    const message = response.status >= 500
      ? init?.method === "POST" ? "The save could not be confirmed. Refresh the snapshot before trying again." : "The API is unavailable. Try loading again."
      : detail?.message ?? (response.status === 404 ? "Hospital not found." : "The request failed. Try again.");
    throw new FacilityClientError(message, response.status, response.status >= 500 ? undefined : detail);
  }
  try { return await response.json() as T; }
  catch { throw new FacilityClientError(init?.method === "POST" ? "The save response could not be read. Refresh the snapshot before submitting again." : "The API response could not be read. Try loading again."); }
}

function demo() {
  try { return createDemoClient(window.localStorage); }
  catch { throw new FacilityClientError("Browser storage is unavailable for this synthetic demo."); }
}

export async function listFacilities(): Promise<FacilityListResponse> {
  return facilityDataMode === "demo" ? demo().listFacilities() : facilityRequest("/api/v1/facilities");
}
export async function getFacilitySnapshot(facility_id: string): Promise<FacilitySnapshotResponse> {
  return facilityDataMode === "demo" ? demo().getFacilitySnapshot(facility_id)
    : facilityRequest(`/api/v1/facilities/${encodeURIComponent(facility_id)}/snapshot`);
}
export async function createResourceObservation(facility_id: string, payload: ObservationCreate): Promise<ObservationResponse> {
  return facilityDataMode === "demo" ? demo().createResourceObservation(facility_id, payload)
    : facilityRequest(`/api/v1/facilities/${encodeURIComponent(facility_id)}/observations`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
}
