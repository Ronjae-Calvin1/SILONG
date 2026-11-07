// Single place that knows how to reach the backend.
// Map slice + status updates + adding/removing/restoring evacuation centers for now — more endpoints get added back as features return.

import type { Facility, FacilityStatus, NewEvacuationCenter, RemovedCenter, StatusPayload } from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";

// Error with a plain-language message that is safe to show to people.
export class ApiError extends Error {
  status: number; // HTTP status, or 0 when the server could not be reached
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// FastAPI sends `detail` as a string (our own errors) or as a list (shape errors).
function messageFromBody(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    const field = first.loc && first.loc.length > 1 ? String(first.loc[first.loc.length - 1]) : "";
    const msg = (first.msg ?? fallback).replace(/^Value error, /, "");
    return field ? `${field.replace(/_/g, " ")}: ${msg}` : msg;
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your internet connection and try again.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, messageFromBody(body, `Something went wrong (error ${res.status}).`));
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  getFacilities: () => request<Facility[]>("/facilities"),
  // Returns the new latest status for that facility.
  submitStatus: (facilityId: number, payload: StatusPayload) =>
    request<FacilityStatus>(`/facilities/${facilityId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  // Returns the new center, shaped like an item of getFacilities().
  addEvacuationCenter: (payload: NewEvacuationCenter) =>
    request<Facility>("/evacuation-centers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  // Soft remove: the backend hides the center and keeps its data, so it can be restored.
  removeEvacuationCenter: (facilityId: number) =>
    request<RemovedCenter>(`/evacuation-centers/${facilityId}`, { method: "DELETE" }),
  // Centers that are removed right now (newest removal first), for the restore list.
  getRemovedCenters: () => request<RemovedCenter[]>("/evacuation-centers/removed"),
  // Brings a removed center back. Returns it shaped like an item of getFacilities().
  restoreEvacuationCenter: (facilityId: number) =>
    request<Facility>(`/evacuation-centers/${facilityId}/restore`, { method: "POST" }),
};
