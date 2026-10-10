/** Live generated-contract aliases shared by mocks, forms and API calls. */
import type { components } from "./schema";
import type { components as DesignComponents } from "./feature-1-schema";

type Schemas = components["schemas"];
export type Facility = Schemas["Facility"];
export type FacilityListResponse = Schemas["FacilityListResponse"];
export type FacilityService = Schemas["FacilityService"];
// The catalog entity has no standalone live endpoint; retain its generated design type.
export type ResourceDefinition = DesignComponents["schemas"]["ResourceDefinition"];
export type ResourceSnapshot = Schemas["ResourceSnapshot"];
export type FacilitySnapshotResponse = Schemas["FacilitySnapshotResponse"];
export type ObservationCreate = Schemas["ObservationCreate"];
export type ObservationResponse = Schemas["ObservationResponse"];
export type ErrorResponse = Schemas["ErrorResponse"];
