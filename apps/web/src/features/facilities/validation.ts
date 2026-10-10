import type { ObservationCreate, ResourceDefinition } from "../../lib/api/feature-1";

export type ObservationErrors = Record<string, string>;

/** Input feedback only. The API remains responsible for authoritative validation. */
export function validateObservationInput(
  resource: ResourceDefinition | undefined,
  quantity: string,
  localTime: string,
  now: Date,
): { payload?: ObservationCreate; errors: ObservationErrors } {
  const errors: ObservationErrors = {};
  const value = Number(quantity);
  const observed = new Date(localTime);
  if (!resource) errors.resource_id = "Select an available resource.";
  if (!quantity.trim() || !Number.isFinite(value) || value < 0) {
    errors.available_quantity = "Enter a finite quantity of zero or more.";
  } else if (resource && !resource.allows_fractional && !Number.isInteger(value)) {
    errors.available_quantity = "This resource requires a whole number.";
  }
  if (!localTime || !Number.isFinite(observed.getTime())) {
    errors.observed_at = "Enter a valid observation date and time.";
  } else if (observed.getTime() > now.getTime() + 5 * 60_000) {
    errors.observed_at = "Observation time may be at most five minutes ahead.";
  }
  if (Object.keys(errors).length || !resource) return { errors };
  return {
    errors,
    payload: {
      resource_id: resource.resource_id,
      available_quantity: value,
      unit: resource.unit,
      observed_at: observed.toISOString(),
    },
  };
}

export function toLocalInput(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}
