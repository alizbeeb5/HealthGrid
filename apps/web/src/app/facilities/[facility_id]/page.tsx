import { FacilityDetails } from "@/features/facilities/facility-details";

export default async function Page({ params }: { params: Promise<{ facility_id: string }> }) {
  const { facility_id } = await params;
  return <FacilityDetails key={facility_id} facilityId={facility_id} />;
}
