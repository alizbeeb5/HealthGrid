import { Suspense } from "react";
import { AllocationDashboard } from "@/features/allocation/allocation-dashboard";
export default function Page() {
  return <Suspense fallback={<p role="status">Loading resource planning…</p>}><AllocationDashboard /></Suspense>;
}
