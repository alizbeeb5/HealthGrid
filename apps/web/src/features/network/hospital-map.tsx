"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { divIcon, latLngBounds } from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { NetworkFacilityResult } from "../../lib/api/network";
import { useExerciseNames } from "../exercise/context";
import { Timestamp } from "../facilities/shared";
import { CapacityBadge, ModeledPlaces } from "./hospital-table";
import { capacityLabels, evidenceWarnings, facilityLink, hasMapLocation } from "./presentation";

const markerColors = { calculated: "#0f766e", unknown: "#b45309", unavailable: "#be123c", not_configured: "#475569" };
const icons = Object.fromEntries(Object.entries(markerColors).map(([status, color]) => [status, divIcon({
  className: "healthgrid-hospital-marker",
  html: `<span style="display:block;width:24px;height:24px;border:3px solid white;border-radius:50%;background:${color};box-shadow:0 1px 6px #0005"></span>`,
  iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -12],
})]));

function FitHospitals({ rows }: { rows: NetworkFacilityResult[] }) {
  const map = useMap();
  useEffect(() => {
    if (rows.length) map.fitBounds(latLngBounds(rows.map((row) => [row.facility.latitude, row.facility.longitude])), { padding: [65, 55], maxZoom: 13, animate: false });
  }, [map, rows]);
  return null;
}

export default function HospitalMap({ rows, returnTo }: { rows: NetworkFacilityResult[]; returnTo: string }) {
  const names = useExerciseNames();
  const [tilesFailed, setTilesFailed] = useState(false);
  const mappable = rows.filter(hasMapLocation);
  return <div>
    {tilesFailed && <p role="status" className="border-b border-amber-200 bg-amber-50 px-5 py-3 text-xs text-amber-950">Base map tiles could not load. Hospital markers, filters, and the comparison table remain available.</p>}
    {mappable.length < rows.length && <p className="px-5 py-3 text-xs text-amber-950">{rows.length - mappable.length} hospital locations cannot be plotted. They remain in the table and summaries.</p>}
    {mappable.length ? <MapContainer center={[mappable[0].facility.latitude, mappable[0].facility.longitude]} zoom={11} scrollWheelZoom={false} className="z-0 h-[380px] w-full bg-slate-100" aria-label="Hospitals offering the selected service">
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" referrerPolicy="strict-origin-when-cross-origin" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' eventHandlers={{ tileerror: () => setTilesFailed(true) }} />
      <FitHospitals rows={mappable} />
      {mappable.map((row) => <Marker key={row.facility.facility_id} position={[row.facility.latitude, row.facility.longitude]} icon={icons[row.capacity.status]} title={`${row.facility.name}: ${capacityLabels[row.capacity.status]}`} alt={row.facility.name} keyboard>
        <Tooltip permanent direction="top" offset={[0, -12]}><span className="font-semibold">{names.hospital(row.facility.facility_id) === row.facility.facility_id ? row.facility.name : names.hospital(row.facility.facility_id)}</span><br />{row.capacity.estimated_capacity === null ? capacityLabels[row.capacity.status] : `${row.capacity.estimated_capacity} modeled places · ${capacityLabels[row.capacity.status]}`}</Tooltip>
        <Popup><div className="min-w-52"><Link href={facilityLink(row.facility.facility_id, returnTo)} className="font-semibold text-teal-800">{row.facility.name}</Link><div className="mt-2"><ModeledPlaces row={row} /></div><div className="mt-2"><CapacityBadge row={row} /></div>
          <p>Bottleneck: {row.capacity.bottleneck_resource_ids.length ? row.capacity.bottleneck_resource_ids.map(names.resource).join(", ") : "Not identified"}</p>
          <ul className="space-y-1">{evidenceWarnings(row).map((warning) => <li key={warning}>{warning}</li>)}</ul>
          <p>Latest report received:<br /><Timestamp value={row.facility.last_reported_at} /></p>
          <Link href={facilityLink(row.facility.facility_id, returnTo)} className="font-semibold text-teal-800">Open hospital →</Link>
        </div></Popup>
      </Marker>)}
    </MapContainer> : <p className="p-8 text-sm text-slate-600">No hospital locations to show in this selection.</p>}
  </div>;
}
