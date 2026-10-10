"use client";

import { useExercise } from "../exercise/context";
import { useRef, useState } from "react";
import type { FacilitySnapshotResponse, ObservationResponse } from "../../lib/api/feature-1";
import { createResourceObservation, FacilityClientError, facilityDataMode } from "../../lib/api/facilities";
import { buttonClass, displayError, panelClass, Timestamp } from "./shared";
import { type ObservationErrors, toLocalInput, validateObservationInput } from "./validation";

const inputClass = "mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-teal-700 focus:outline-2 focus:outline-teal-100 aria-[invalid=true]:border-rose-500";

export function ObservationForm({ snapshot, onSaved, onRefresh }: {
  snapshot: FacilitySnapshotResponse;
  onSaved: () => Promise<void>;
  onRefresh: () => Promise<void>;
}) {
  const exercise = useExercise();
  const [resourceId, setResourceId] = useState(snapshot.resources[0]?.resource_id ?? "");
  const [quantity, setQuantity] = useState("");
  const [observedAt, setObservedAt] = useState(toLocalInput(new Date(snapshot.as_of)));
  const [errors, setErrors] = useState<ObservationErrors>({});
  const [message, setMessage] = useState<string>();
  const [saved, setSaved] = useState<ObservationResponse>();
  const [pending, setPending] = useState(false);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [refreshWarning, setRefreshWarning] = useState<string>();
  const lock = useRef(false);
  const errorSummary = useRef<HTMLDivElement>(null);
  const resource = snapshot.resources.find((item) => item.resource_id === resourceId);

  function clearFeedback() { setErrors({}); setMessage(undefined); setSaved(undefined); setRefreshWarning(undefined); }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current || needsRefresh) return;
    clearFeedback();
    const validation = validateObservationInput(resource, quantity, observedAt, new Date(exercise?.clock ?? (facilityDataMode === "demo" ? snapshot.as_of : Date.now())));
    if (!validation.payload) {
      setErrors(validation.errors); setMessage("Review the highlighted fields.");
      requestAnimationFrame(() => errorSummary.current?.focus());
      return;
    }
    lock.current = true; setPending(true);
    try {
      const result = await createResourceObservation(snapshot.facility.facility_id, validation.payload);
      setSaved(result); setQuantity("");
      try { await onSaved(); }
      catch { setRefreshWarning("The observation was saved, but the snapshot could not refresh. Reload it to see the latest reports."); setNeedsRefresh(true); }
    } catch (error) {
      setMessage(displayError(error));
      if (error instanceof FacilityClientError && error.detail) {
        setErrors(Object.fromEntries(error.detail.fields.map((field) => [field.field, field.message])));
      }
      const ambiguousSave = !(error instanceof FacilityClientError)
        || (facilityDataMode === "api" && (error.status === undefined || error.status >= 500));
      if (ambiguousSave) setNeedsRefresh(true);
      requestAnimationFrame(() => errorSummary.current?.focus());
    } finally { lock.current = false; setPending(false); }
  }

  async function refresh() {
    setPending(true);
    try { await onRefresh(); setNeedsRefresh(false); setRefreshWarning(undefined); setMessage(undefined); }
    catch (error) { setMessage(displayError(error)); }
    finally { setPending(false); }
  }

  if (!snapshot.resources.length) return <aside className={`${panelClass} p-6`}><h2 className="font-semibold">Record an update</h2><p className="mt-3 text-sm text-slate-600">No applicable resources are configured for this hospital yet.</p></aside>;

  return <aside className={`${panelClass} h-fit p-6`}>
    <h2 className="text-lg font-semibold">Record an update</h2>
    <p className="mt-2 text-sm text-slate-600">Report the quantity available at the time you observed it.</p>
    <form noValidate onSubmit={submit} className="mt-5 space-y-5" aria-busy={pending}>
      {message && <div ref={errorSummary} tabIndex={-1} role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
        <p>{message}</p>{Object.keys(errors).length > 0 && <ul className="mt-2 list-disc pl-4">{Object.entries(errors).map(([key, value]) => <li key={key}>{value}</li>)}</ul>}
      </div>}
      {saved && <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
        <strong>Observation saved{facilityDataMode === "demo" ? " in this browser" : ""}.</strong>
        <p className="mt-1">{saved.available_quantity} {saved.unit} · Observed <Timestamp value={saved.observed_at} /></p>
        <p className="mt-1">The snapshot shows the latest observation. Older reports remain in history.</p>
      </div>}
      {refreshWarning && <p role="alert" className="text-sm text-amber-900">{refreshWarning}</p>}
      <fieldset disabled={pending || needsRefresh} className="space-y-5 disabled:opacity-60">
        <div><label htmlFor="resource-id" className="text-sm font-semibold">Resource</label>
          <select id="resource-id" value={resourceId} onChange={(event) => { setResourceId(event.target.value); clearFeedback(); }} className={inputClass} aria-invalid={!!errors.resource_id} aria-describedby={errors.resource_id ? "resource-error" : undefined}>
            {snapshot.resources.map((item) => <option key={item.resource_id} value={item.resource_id}>{item.name}</option>)}
          </select>{errors.resource_id && <p id="resource-error" className="mt-1 text-xs text-rose-700">{errors.resource_id}</p>}
        </div>
        <div><label htmlFor="quantity" className="text-sm font-semibold">Available quantity <span className="font-normal text-slate-500">({resource?.unit})</span></label>
          <input id="quantity" type="number" min="0" step={resource?.allows_fractional ? "any" : "1"} value={quantity} onChange={(event) => { setQuantity(event.target.value); clearFeedback(); }} className={inputClass} placeholder="Enter quantity" required aria-invalid={!!errors.available_quantity} aria-describedby={`quantity-hint${errors.available_quantity ? " quantity-error" : ""}`} />
          <p id="quantity-hint" className="mt-1.5 text-xs text-slate-500">{resource?.allows_fractional ? "Fractional quantities allowed." : "Whole numbers only."} Zero means known zero availability.</p>
          {errors.available_quantity && <p id="quantity-error" className="mt-1 text-xs text-rose-700">{errors.available_quantity}</p>}
          {errors.unit && <p role="alert" className="mt-1 text-xs text-rose-700">{errors.unit}</p>}
        </div>
        <div><label htmlFor="observed-at" className="text-sm font-semibold">Observation time</label>
          <input id="observed-at" type="datetime-local" value={observedAt} onChange={(event) => { setObservedAt(event.target.value); clearFeedback(); }} className={inputClass} required aria-invalid={!!errors.observed_at} aria-describedby={`time-hint${errors.observed_at ? " time-error" : ""}`} />
          <p id="time-hint" className="mt-1.5 text-xs text-slate-500">Your local timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone}). Sent in UTC. Older reports are accepted.</p>
          {errors.observed_at && <p id="time-error" className="mt-1 text-xs text-rose-700">{errors.observed_at}</p>}
        </div>
        <button type="submit" className={`${buttonClass} w-full`}>{pending ? "Saving…" : "Save observation"}</button>
      </fieldset>
      {needsRefresh && <button type="button" className={`${buttonClass} w-full`} disabled={pending} onClick={refresh}>{pending ? "Refreshing…" : "Refresh snapshot before another update"}</button>}
    </form>
  </aside>;
}
