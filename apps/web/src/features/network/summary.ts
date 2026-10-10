import type { Facility } from "../../lib/api/feature-1";
import type { ServiceCapacityResult } from "../../lib/api/feature-2";

/** Display-only projection of generated types, not a competing wire schema.
 * A generated NetworkFacilityResult[] can be passed directly when published.
 */
export type NetworkSummaryRow = {
  facility: Pick<Facility, "facility_id">;
  capacity: Pick<
    ServiceCapacityResult,
    "service_id" | "status" | "estimated_capacity" | "profile_version" | "capacity_unit"
  >;
};

export type NetworkSummary = {
  facility_count: number;
  calculated_count: number;
  unavailable_count: number;
  unknown_count: number;
  not_configured_count: number;
  known_estimate_count: number;
  unresolved_count: number;
  modeled_capacity_subtotal: number | null;
  subtotal_status: "available" | "no_known_estimates" | "incompatible_profiles";
  attention_facility_ids: string[];
};

/** Summarize already-filtered rows for ONE service without recalculating capacity.
 * Known estimates include unavailable zeros. Unknown values are never made zero.
 * A subtotal assumes independent hospital resources and must show its coverage.
 */
export function summarizeNetwork(rows: readonly NetworkSummaryRow[]): NetworkSummary {
  const summary: NetworkSummary = {
    facility_count: rows.length,
    calculated_count: 0,
    unavailable_count: 0,
    unknown_count: 0,
    not_configured_count: 0,
    known_estimate_count: 0,
    unresolved_count: 0,
    modeled_capacity_subtotal: null,
    subtotal_status: "no_known_estimates",
    attention_facility_ids: [],
  };
  const serviceId = rows[0]?.capacity.service_id;
  const seen = new Set<string>();
  const known: NetworkSummaryRow["capacity"][] = [];
  const attention: { id: string; priority: number }[] = [];

  for (const { facility, capacity } of rows) {
    if (capacity.service_id !== serviceId) {
      throw new Error("Network summaries must contain only one service.");
    }
    if (seen.has(facility.facility_id)) {
      throw new Error(`Duplicate facility in network summary: ${facility.facility_id}`);
    }
    seen.add(facility.facility_id);
    const estimate = capacity.estimated_capacity;
    const isKnown = capacity.status === "calculated" || capacity.status === "unavailable";
    if (isKnown) {
      if (estimate === null || !Number.isSafeInteger(estimate) || estimate < 0) {
        throw new Error("Known estimates must be nonnegative safe integers.");
      }
      if (capacity.status === "unavailable" && estimate !== 0) {
        throw new Error("An unavailable service must have an estimate of zero.");
      }
      known.push(capacity);
    } else if (estimate !== null) {
      throw new Error("Unresolved estimates must remain null.");
    }

    switch (capacity.status) {
      case "calculated":
        summary.calculated_count++;
        if (estimate === 0) attention.push({ id: facility.facility_id, priority: 1 });
        break;
      case "unavailable":
        summary.unavailable_count++;
        attention.push({ id: facility.facility_id, priority: 0 });
        break;
      case "unknown":
        summary.unknown_count++;
        attention.push({ id: facility.facility_id, priority: 2 });
        break;
      case "not_configured":
        summary.not_configured_count++;
        attention.push({ id: facility.facility_id, priority: 3 });
        break;
      default:
        throw new Error("Unrecognized capacity status.");
    }
  }

  summary.known_estimate_count = known.length;
  summary.unresolved_count = summary.unknown_count + summary.not_configured_count;
  summary.attention_facility_ids = attention.sort((a, b) =>
    a.priority - b.priority || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
  ).map(({ id }) => id);

  if (known.length > 0) {
    const first = known[0];
    const compatible = first.profile_version != null && first.capacity_unit != null &&
      known.every(row => row.profile_version === first.profile_version &&
        row.capacity_unit === first.capacity_unit);
    if (!compatible) {
      summary.subtotal_status = "incompatible_profiles";
    } else {
      const subtotal = known.reduce((sum, row) => sum + row.estimated_capacity!, 0);
      if (!Number.isSafeInteger(subtotal)) {
        throw new Error("Network subtotal exceeds safe integer precision.");
      }
      summary.subtotal_status = "available";
      summary.modeled_capacity_subtotal = subtotal;
    }
  }
  return summary;
}
