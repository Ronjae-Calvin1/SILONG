// Labels and small helpers for the capacity / availability feature.

import type { Facility, FacilityType, ResourceName, StatusValue } from "../types";

export const TYPE_LABEL: Record<FacilityType, string> = {
  hospital: "Hospital",
  clinic: "Clinic",
  evacuation_center: "Evacuation center",
};

// Status buttons per facility type, in display order (wording from the project documentation).
export const STATUS_OPTIONS: Record<FacilityType, { value: StatusValue; label: string }[]> = {
  evacuation_center: [
    { value: "open", label: "Open - Space available" },
    { value: "almost_full", label: "Almost full" },
    { value: "full", label: "Full" },
    { value: "closed", label: "Closed / Not in use" },
  ],
  hospital: [
    { value: "open", label: "Open - Accepting patients" },
    { value: "busy", label: "Busy / Limited" },
    { value: "full", label: "Full / Not accepting" },
    { value: "closed", label: "Closed" },
  ],
  clinic: [
    { value: "open", label: "Open - Accepting patients" },
    { value: "busy", label: "Busy / Limited" },
    { value: "full", label: "Full / Not accepting" },
    { value: "closed", label: "Closed" },
  ],
};

export const RESOURCE_OPTIONS: { value: ResourceName; label: string }[] = [
  { value: "space", label: "Space" },
  { value: "food", label: "Food" },
  { value: "water", label: "Water" },
  { value: "power", label: "Power" },
  { value: "toilets", label: "Toilets" },
  { value: "medical", label: "Medical" },
];

export const NOTE_MAX = 140; // same limit as the backend

// "No status yet" is never shown as a fake default like "Open".
export function statusLabel(f: Facility): string {
  if (!f.status) return "No status yet";
  return STATUS_OPTIONS[f.type].find((o) => o.value === f.status!.status)?.label ?? f.status.status;
}

// Drives the pin color and the badge color.
export function statusKey(f: Facility): StatusValue | "unknown" {
  return f.status ? f.status.status : "unknown";
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"} ago`;
}

// "just now", "15 minutes ago", "3 hours ago", "2 days ago"
export function timeAgo(iso: string, now: number): string {
  const secs = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return plural(mins, "minute");
  const hours = Math.floor(mins / 60);
  if (hours < 24) return plural(hours, "hour");
  return plural(Math.floor(hours / 24), "day");
}

// Local clock time; adds the date when the update is not from today.
export function clockTime(iso: string, now: number): string {
  const d = new Date(iso);
  const sameDay = d.toDateString() === new Date(now).toDateString();
  return sameDay
    ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

// Some contacts hold several numbers ("+6343 123;+6343 456 local 12"). One link each;
// anything after "local" is an extension and is left out of the dialed number.
export function phoneLinks(contact?: string): { text: string; href: string }[] {
  if (!contact || contact === "N/A") return [];
  return contact
    .split(";")
    .map((t) => t.trim())
    .filter(Boolean)
    .map((text) => ({ text, href: `tel:${text.split(/local|loc\./i)[0].replace(/[^\d+]/g, "")}` }));
}
