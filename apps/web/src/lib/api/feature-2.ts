/** Aliases from the backend-owned Pydantic/OpenAPI contract. */
import type { components } from "./schema";

type Schemas = components["schemas"];
export type FacilityCapacityResponse = Schemas["FacilityCapacityResponse"];
export type ServiceCapacityResult = Schemas["ServiceCapacityResult"];
export type ResourceCapacityLimit = Schemas["ResourceCapacityLimit"];
