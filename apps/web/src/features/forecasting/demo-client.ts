import examples from "../../lib/api/forecast-fixtures.generated.json";
import facilities from "../../lib/api/facilities-fixtures.generated.json";
import { facilityRequest } from "../../lib/api/facilities";
import type { components } from "../../lib/api/schema";
import type { FacilityListResponse, FacilitySnapshotResponse } from "../../lib/api/feature-1";

export type ForecastResponse = components["schemas"]["FacilityForecastResponse"];
export type ForecastMode = "api" | "example";
export function forecastCatalog(): { facility: FacilityListResponse["items"][number]; services: { service_id: string; name: string }[] }[] {
  return facilities.list.items.map((facility) => ({ facility,
    services: facilities.snapshots[facility.facility_id as keyof typeof facilities.snapshots].services.map(({ service_id, name }) => ({ service_id, name })),
  }));
}
export async function loadForecastCatalog(mode: ForecastMode) {
  if (mode === "example") return forecastCatalog();
  const list = await facilityRequest<FacilityListResponse>("/api/v1/facilities");
  return Promise.all(list.items.map(async (facility) => {
    const snapshot = await facilityRequest<FacilitySnapshotResponse>(`/api/v1/facilities/${encodeURIComponent(facility.facility_id)}/snapshot`);
    return { facility, services: snapshot.services.map(({ service_id, name }) => ({ service_id, name })) };
  }));
}
/** Presentation aliases only. All quantities and alerts come from Python output. */
export function presentForecast(response: ForecastResponse) {
  const first = response.alerts[0];
  const point = response.forecast.find((day) => day.date === first?.date);
  return { ...response,
    as_of: response.generated_at,
    baseline_capacity: response.history.at(-1)?.capacity ?? null,
    history_days_available: response.history.length,
    forecast: response.forecast.map((day) => ({ ...day, capacity: day.predicted_capacity, demand: day.predicted_demand, gap: day.expected_gap })),
    first_gap: first && point ? { date: first.date, day_number: response.forecast.findIndex((day) => day.date === first.date) + 1, capacity: point.predicted_capacity, demand: point.predicted_demand, gap: first.expected_gap } : null,
  };
}
export type ForecastPreview = ReturnType<typeof presentForecast>;
export type ForecastDay = ForecastPreview["forecast"][number];
export async function getForecastExample(facilityId: string, serviceId: string): Promise<ForecastPreview> {
  const example = examples.find((item) => item.facility_id === facilityId && item.service_id === serviceId);
  if (!example) throw new Error("No forecast preview is available for this hospital and service. Use API mode or select a shared example.");
  return presentForecast(structuredClone(example) as ForecastResponse);
}
export function getForecast(facilityId: string, serviceId: string) {
  return facilityRequest<ForecastResponse>(`/api/v1/forecasts/facilities/${encodeURIComponent(facilityId)}?${new URLSearchParams({ service_id: serviceId })}`).then(presentForecast);
}
