import catalog from "../../lib/api/facilities-fixtures.generated.json";
import type { FacilitySnapshotResponse } from "../../lib/api/feature-1";
import type { components } from "../../lib/api/schema";
import type { ServiceCapacityResult } from "../../lib/api/feature-2";

/** Backend-owned wire types; presentation aliases below contain no calculations. */
export type ServiceOverride = components["schemas"]["ServiceOverride"];
export type ResourceOverride = components["schemas"]["ResourceOverride"];
export type IncidentFields = components["schemas"]["IncidentDraftInput"];
export type PreviewRevision = {
  incident_id: string; revision_id: string; parent_revision_id: string | null;
  status: "draft" | "confirmed"; input: IncidentFields; created_at: string;
  confirmed_at: string | null; confirmed_by: string | null;
  baseline_id?: string | null;
  baseline: { captured_at: string; baseline_id: string; rows: Pick<ComparisonRow, "facility_id" | "name" | "baseline">[]; facility_snapshots: FacilitySnapshotResponse[]; requirement_profiles: { service_id: string; profile_version: string; capacity_unit: string; requirements: { resource_id: string; unit: string; required_per_capacity_unit: number }[] }[] } | null;
};
export type ComparisonRow = {
  facility_id: string; name: string; affected: boolean;
  baseline: ServiceCapacityResult; scenario: ServiceCapacityResult; capacity_change: number | null;
  applied_overrides?: components["schemas"]["ImpactRow"]["applied_overrides"];
};
export type PreviewRun = { run_id: string; revision_id: string; incident_id: string; created_at: string; engine_version: string; baseline_id: string; baseline_at: string; input: IncidentFields; rows: ComparisonRow[] };
export type ReviewAnswer = { question: string; value: "yes" | "no" | "unclear" | null; answer_status: "answered" | "refused" };
export type Assessment = { status: "completed" | "unavailable" | "failed" | "refused"; answers: ReviewAnswer[]; model: string | null; elapsed_ms: number | null; rubric_version: string; message: string };
export type Extraction = { status: "completed" | "unavailable" | "failed" | "refused"; candidate: IncidentFields | null; evidence: { field_path: string; source_excerpt: string }[]; questions: string[]; warnings: string[]; model: string | null; elapsed_ms: number | null; message: string };
export const snapshots = Object.values(catalog.snapshots) as FacilitySnapshotResponse[];
export const blankIncident = (): IncidentFields => ({ title: "", report_text: null, service_id: "emergency-care", starts_at: null, expected_ends_at: null, affected_facility_ids: [], service_overrides: [], resource_overrides: [], assumptions: [] });
export const outageReport = "Demo Hospital B's emergency service is unavailable after a power failure. The disruption started at 10:00 UTC on October 10, 2026 and is expected to last six hours.";
export const outageExample = (): IncidentFields => ({ title: "Hospital B power failure", report_text: outageReport, service_id: "emergency-care", starts_at: "2026-10-10T10:00:00Z", expected_ends_at: "2026-10-10T16:00:00Z", affected_facility_ids: ["DEMO-B"], service_overrides: [{ facility_id: "DEMO-B", service_id: "emergency-care", status: "unavailable", restriction_note: "Power failure; emergency service unavailable." }], resource_overrides: [], assumptions: ["Unavailable service is modeled as one post-incident state; recovery is not simulated."] });

/** Input feedback only, no capacity/impact calculation. */
export function validateIncident(input: IncidentFields, confirming: boolean, available = snapshots): string[] {
  const errors: string[] = [];
  if (!input.title.trim() || input.title.length > 200) errors.push("Title must contain 1–200 characters.");
  if ((input.report_text?.length ?? 0) > 10000) errors.push("Report must be at most 10,000 characters.");
  for (const [name, value] of [["Start", input.starts_at], ["End", input.expected_ends_at]]) {
    if (value && (!Number.isFinite(Date.parse(value)) || !value.endsWith("Z"))) errors.push(`${name} must be a valid UTC timestamp.`);
  }
  if (input.starts_at && input.expected_ends_at && Date.parse(input.expected_ends_at) <= Date.parse(input.starts_at)) errors.push("End must be after start.");
  if (input.assumptions.some((item) => !item.trim() || item.length > 500)) errors.push("Each assumption must contain 1–500 characters.");
  if (new Set(input.affected_facility_ids).size !== input.affected_facility_ids.length) errors.push("Affected hospitals must be unique.");
  for (const id of input.affected_facility_ids) {
    const hospital = available.find((item) => item.facility.facility_id === id);
    if (!hospital || (input.service_id && !hospital.services.some((item) => item.service_id === input.service_id))) errors.push(`${id} must offer the selected service.`);
  }
  const pairs = new Set<string>();
  for (const override of input.service_overrides) {
    const pair = `service:${override.facility_id}:${override.service_id}`;
    if (pairs.has(pair)) errors.push("Duplicate service override."); pairs.add(pair);
    if (!input.affected_facility_ids.includes(override.facility_id) || override.service_id !== input.service_id) errors.push("Service overrides must belong to an affected hospital and selected service.");
    if (override.status === "limited" && !override.restriction_note?.trim()) errors.push("A limited service requires a restriction note; capacity stays unknown.");
  }
  for (const override of input.resource_overrides) {
    const pair = `resource:${override.facility_id}:${override.resource_id}`;
    if (pairs.has(pair)) errors.push("Duplicate resource override."); pairs.add(pair);
    const resource = available.find((item) => item.facility.facility_id === override.facility_id)?.resources.find((item) => item.resource_id === override.resource_id);
    if (!input.affected_facility_ids.includes(override.facility_id) || !resource || resource.unit !== override.unit) errors.push("Resource overrides require an applicable hospital resource and its catalog unit.");
    if (!Number.isFinite(override.available_quantity) || override.available_quantity < 0 || (resource && !resource.allows_fractional && !Number.isInteger(override.available_quantity))) errors.push("Resource quantities must be finite, nonnegative and whole where required.");
  }
  if (confirming) {
    if (!input.service_id || !input.starts_at || !input.affected_facility_ids.length) errors.push("Confirmation requires a service, start time and affected hospital.");
    if (!input.service_overrides.length && !input.resource_overrides.length) errors.push("Confirmation requires at least one explicit service or resource override.");
  }
  return [...new Set(errors)];
}
