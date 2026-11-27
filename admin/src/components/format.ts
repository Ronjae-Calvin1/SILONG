import type { AdminReport, Place } from "../api/types";

// The server has only the number `id`. Same look as the user site: SIL- plus 4 digits.
export const reference = (id: number) => `SIL-${String(id).padStart(4, "0")}`;

export function timeAgo(iso: string, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hr ago`;
  const d = Math.floor(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

export function distanceText(m: number | null): string | null {
  if (m === null || m === undefined) return null;
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;
}

function haversineM(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const rad = Math.PI / 180;
  const dLat = (bLat - aLat) * rad;
  const dLng = (bLng - aLng) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(aLat * rad) * Math.cos(bLat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

// The server gives no place name for a report: coordinates, plus the nearest facility within 2 km.
export function placeText(r: AdminReport, places: Place[]): string {
  const coords = `${r.latitude.toFixed(4)}, ${r.longitude.toFixed(4)}`;
  let best: Place | null = null;
  let bestD = Infinity;
  for (const p of places) {
    const d = haversineM(r.latitude, r.longitude, p.latitude, p.longitude);
    if (d < bestD) {
      best = p;
      bestD = d;
    }
  }
  return best && bestD <= 2000 ? `${coords} · near ${best.name}` : coords;
}

export const isOpen = (r: AdminReport) => r.status === "new" || r.status === "being_handled";

export const reportTitle = (r: AdminReport) =>
  (r.category ?? (r.kind === "help" ? "Help needed" : "Hazard")) + (r.kind === "hazard" && r.report_count > 1 ? ` · ${r.report_count} reports` : "");

// Google Maps directions, as decided.
export const navigateUrl = (r: AdminReport) =>
  `https://www.google.com/maps/dir/?api=1&destination=${r.latitude},${r.longitude}`;
