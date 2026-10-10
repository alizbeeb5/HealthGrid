import type { ErrorResponse } from "./feature-1";

export class FacilityClientError extends Error {
  constructor(message: string, public status?: number, public detail?: ErrorResponse["error"]) {
    super(message);
    this.name = "FacilityClientError";
  }
}
