"use client";

import { useEffect, useMemo, useState } from "react";
import { getCapacityExample, getFacilityCapacity, hasCapacityExample } from "../../lib/api/capacity";
import { facilityDataMode } from "../../lib/api/facilities";
import { createCapacityLoader, type CapacityState } from "./capacity-loader";

export function useCapacity(facilityId: string) {
  const [state, setState] = useState<CapacityState>({ phase: "loading" });
  const loader = useMemo(() => createCapacityLoader(() => {
    if (facilityDataMode === "demo") {
      return Promise.reject(new Error("Capacity cannot be refreshed for browser-only demo observations. The synthetic example is frozen and does not include saved updates."));
    }
    return getFacilityCapacity(facilityId);
  }, setState), [facilityId]);
  useEffect(() => {
    if (facilityDataMode === "demo" && hasCapacityExample(facilityId)) loader.showExample(getCapacityExample(facilityId));
    else void loader.refresh();
    return () => loader.cancel();
  }, [loader, facilityId]);

  return {
    state,
    refresh: () => loader.refresh(),
    showExample: facilityDataMode === "demo" && hasCapacityExample(facilityId) ? () => loader.showExample(getCapacityExample(facilityId)) : undefined,
  };
}
