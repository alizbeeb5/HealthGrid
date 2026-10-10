import bundledExamples from "./facilities-fixtures.generated.json";
import type { FacilityListResponse, FacilitySnapshotResponse, ObservationCreate, ObservationResponse } from "./feature-1";
import { FacilityClientError } from "./facilities-error";

const listExample = bundledExamples.list;
const fixtures = bundledExamples.snapshots as Record<string, FacilitySnapshotResponse>;
const fixtureTime = Math.max(...Object.values(fixtures).map((snapshot) => Date.parse(snapshot.as_of)));
const storageKey = "healthgrid:synthetic-observations:v1";

/** Synthetic observations are stored only in this browser; no production persistence. */
export function createDemoClient(storage: Pick<Storage, "getItem" | "setItem">) {
  function readHistory(): ObservationResponse[] {
    try {
      const parsed: unknown = JSON.parse(storage.getItem(storageKey) ?? "[]");
      if (!Array.isArray(parsed) || !parsed.every((entry) => {
        if (!entry || typeof entry !== "object") return false;
        const resource = fixtures[entry.facility_id]?.resources.find((item) => item.resource_id === entry.resource_id);
        return resource && resource.unit === entry.unit && typeof entry.observation_id === "string"
          && typeof entry.available_quantity === "number" && Number.isFinite(entry.available_quantity)
          && entry.available_quantity >= 0 && (resource.allows_fractional || Number.isInteger(entry.available_quantity))
          && typeof entry.observed_at === "string" && Number.isFinite(Date.parse(entry.observed_at))
          && typeof entry.recorded_at === "string" && Number.isFinite(Date.parse(entry.recorded_at));
      })) throw new Error("Invalid stored observations");
      return parsed;
    } catch {
      throw new FacilityClientError("Browser demo data could not be read. Check browser storage permissions or clear this site's demo data.");
    }
  }

  function requireFixture(id: string): FacilitySnapshotResponse {
    if (!Object.hasOwn(fixtures, id)) {
      throw new FacilityClientError("Hospital not found.", 404, {
        code: "facility_not_found", message: "Hospital not found.", fields: [],
      });
    }
    return structuredClone(fixtures[id]);
  }

  function demoTime(history: ObservationResponse[]): number {
    return Math.max(fixtureTime, ...history.map((item) => Date.parse(item.recorded_at)));
  }

  async function getFacilitySnapshot(id: string): Promise<FacilitySnapshotResponse> {
    const snapshot = requireFixture(id);
    const history = readHistory();
    const observations = history.filter((item) => item.facility_id === id);
    snapshot.as_of = new Date(demoTime(history)).toISOString();
    for (const resource of snapshot.resources) {
      const candidates: ObservationResponse[] = observations.filter((item) => item.resource_id === resource.resource_id);
      if (resource.observation_id && resource.observed_at && resource.recorded_at && resource.available_quantity !== null) {
        candidates.push({
          resource_id: resource.resource_id, unit: resource.unit, available_quantity: resource.available_quantity,
          facility_id: id, observation_id: resource.observation_id, observed_at: resource.observed_at, recorded_at: resource.recorded_at,
        });
      }
      candidates.sort((a, b) => Date.parse(b.observed_at) - Date.parse(a.observed_at)
        || Date.parse(b.recorded_at) - Date.parse(a.recorded_at)
        || (a.observation_id < b.observation_id ? 1 : a.observation_id > b.observation_id ? -1 : 0));
      const latest = candidates[0];
      if (latest) {
        resource.observation_id = latest.observation_id;
        resource.available_quantity = latest.available_quantity;
        resource.observed_at = latest.observed_at;
        resource.recorded_at = latest.recorded_at;
        resource.data_status = Date.parse(snapshot.as_of) - Date.parse(latest.observed_at) > snapshot.stale_after_hours * 3_600_000 ? "stale" : "current";
      }
    }
    snapshot.facility.last_reported_at = observations.reduce((latest, item) =>
      !latest || Date.parse(item.recorded_at) > Date.parse(latest) ? item.recorded_at : latest,
    snapshot.facility.last_reported_at);
    return snapshot;
  }

  async function listFacilities(): Promise<FacilityListResponse> {
    return { items: await Promise.all(listExample.items.map(async (facility) => (await getFacilitySnapshot(facility.facility_id)).facility)) };
  }

  async function createResourceObservation(id: string, payload: ObservationCreate): Promise<ObservationResponse> {
    const snapshot = requireFixture(id);
    const history = readHistory();
    const resource = snapshot.resources.find((item) => item.resource_id === payload.resource_id);
    const fields = [];
    if (!resource) fields.push({ field: "resource_id", message: "Select a resource applicable to this hospital." });
    if (resource && payload.unit !== resource.unit) fields.push({ field: "unit", message: `Expected ${resource.unit}.` });
    if (!Number.isFinite(payload.available_quantity) || payload.available_quantity < 0
      || (resource && !resource.allows_fractional && !Number.isInteger(payload.available_quantity))) {
      fields.push({ field: "available_quantity", message: "Enter a nonnegative quantity in the allowed increments." });
    }
    const observed = Date.parse(payload.observed_at);
    if (!Number.isFinite(observed) || !/(Z|[+-]\d{2}:\d{2})$/.test(payload.observed_at) || observed > demoTime(history) + 300_000) {
      fields.push({ field: "observed_at", message: "Use a timezone-aware time no more than five minutes ahead of the demo clock." });
    }
    if (fields.length) throw new FacilityClientError("The observation could not be saved.", 422, {
      code: "invalid_observation", message: "The observation could not be saved.", fields,
    });
    const saved: ObservationResponse = {
      ...payload, observed_at: new Date(observed).toISOString(), facility_id: id,
      observation_id: `OBS-${crypto.randomUUID()}`, recorded_at: new Date(demoTime(history) + 1000).toISOString(),
    };
    try { storage.setItem(storageKey, JSON.stringify([...history, saved])); }
    catch { throw new FacilityClientError("The demo update could not be stored. Check browser storage permissions and available space."); }
    return saved;
  }

  return { listFacilities, getFacilitySnapshot, createResourceObservation };
}
