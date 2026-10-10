import type { NetworkFacilityResult, NetworkService } from "../../lib/api/network";
import demoCatalog from "../../lib/api/facilities-fixtures.generated.json";

export const capacityLabels = {
  calculated: "Calculated", unknown: "Unknown", unavailable: "Unavailable", not_configured: "Not configured",
};
export type CapacityFilter = "all" | keyof typeof capacityLabels;

export function capacityFilter(value: string | null): CapacityFilter {
  return value && Object.hasOwn(capacityLabels, value) ? value as CapacityFilter : "all";
}

export function filterHospitals(rows: NetworkFacilityResult[], name: string, status: CapacityFilter) {
  const query = name.trim().toLocaleLowerCase();
  return rows.filter((row) => row.facility.name.toLocaleLowerCase().includes(query)
    && (status === "all" || row.capacity.status === status));
}

export function initialService(services: NetworkService[], requested: string | null) {
  if (requested !== null) return requested;
  return services.find((item) => item.service_id === "emergency-care")?.service_id
    ?? [...services].sort((a, b) => a.service_id < b.service_id ? -1 : a.service_id > b.service_id ? 1 : 0)[0]?.service_id;
}

export function facilityLink(id: string, overviewPath: string) {
  return `/facilities/${encodeURIComponent(id)}?${new URLSearchParams({ return_to: overviewPath })}`;
}

export function resourceLabel(id: string) {
  // The network wire contract exposes IDs, not a resource catalog. Label known
  // demo IDs from the shared catalog; preserve other IDs without inventing names.
  return Object.values(demoCatalog.snapshots).flatMap((snapshot) => snapshot.resources)
    .find((resource) => resource.resource_id === id)?.name ?? id;
}

export function evidenceWarnings(row: NetworkFacilityResult): string[] {
  const explanations: Record<string, string> = {
    service_unavailable: "Service reported unavailable.",
    requirements_not_configured: "No calculation profile configured.",
    service_restriction_unquantified: "Service restriction is not quantified.",
    missing_required_observation: "Required resource reports are missing.",
    stale_required_observation: "Required resource reports are outdated.",
  };
  const warnings = row.capacity.reason_codes.map((code) => explanations[code] ?? code);
  if (row.capacity.status === "calculated" && row.capacity.estimated_capacity === 0) warnings.unshift("Reported resources support zero modeled places.");
  return warnings;
}

export function hasMapLocation(row: NetworkFacilityResult) {
  return Number.isFinite(row.facility.latitude) && Math.abs(row.facility.latitude) <= 90
    && Number.isFinite(row.facility.longitude) && Math.abs(row.facility.longitude) <= 180;
}
