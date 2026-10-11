import { LocalizedText } from "@/lib/i18n/context";
import { Suspense } from "react";
import { AllocationDashboard } from "@/features/allocation/allocation-dashboard";
export default function Page() {
  return <Suspense fallback={<p role="status"><LocalizedText>Loading resource planning…</LocalizedText></p>}><AllocationDashboard /></Suspense>;
}
