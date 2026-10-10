import { FacilityDetails } from "@/features/facilities/facility-details";
import { overviewReturnPath } from "@/features/network/return-navigation";

export default async function Page({ params, searchParams }: { params: Promise<{ facility_id: string }>; searchParams: Promise<{ return_to?: string | string[] }> }) {
  const { facility_id } = await params;
  const { return_to } = await searchParams;
  return <FacilityDetails key={facility_id} facilityId={facility_id} returnTo={overviewReturnPath(return_to)} />;
}
