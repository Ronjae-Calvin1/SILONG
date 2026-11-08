// Labels and small helpers for the capacity / availability feature.

import type { Facility, FacilityStatus, FacilityType, ResourceName, StatusValue } from "../types";

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

// "1 person" / "85 people", "1 space" / "15 spaces"
export function countOf(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

// Bar color for the capacity indicator: under 70% green, 70-99% orange, 100% or more red.
// Worked out from the real counts (not the rounded percent_full), so 9,999 of 10,000
// can never round up to a red "100%".
export type CapacityLevel = "green" | "orange" | "red";

export function capacityLevel(people: number, max: number): CapacityLevel {
  if (people >= max) return "red";
  return people * 100 >= max * 70 ? "orange" : "green";
}

// Same rule as the backend's capacity_fields(): the new report's max_capacity (the server
// already filled it in from the last known one when the form left it out), people_inside
// from the report, and the numbers that depend on both. Lets the panel and pin show a new
// report right away without waiting for the next refresh.
export function withNewStatus(f: Facility, s: FacilityStatus): Facility {
  const next: Facility = { ...f, status: s, is_outdated: s.is_outdated };
  if (f.type !== "evacuation_center") return next;
  const max = s.max_capacity ?? f.max_capacity;
  const people = s.people_inside;
  const known = people !== null && max !== null;
  return {
    ...next,
    people_inside: people,
    max_capacity: max,
    spaces_left: known ? Math.max(0, max - people) : null,
    percent_full: known ? Math.round((people / max) * 1000) / 10 : null,
  };
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

// ---------- Added for the redesigned details panel and status form ----------

// A small symbol shown next to every status, so the status is never shown by color alone.
export const STATUS_SYMBOL: Record<StatusValue | "unknown", string> = {
  open: "\u2713", // check mark
  almost_full: "!",
  busy: "!",
  full: "\u2715", // cross
  closed: "\u2013", // dash
  unknown: "?",
};

// One short helper line under each status choice in the update form.
const STATUS_HINT: Record<FacilityType, Partial<Record<StatusValue, string>>> = {
  evacuation_center: {
    open: "Accepting more people.",
    almost_full: "Only a few spaces are left.",
    full: "Cannot take more people.",
    closed: "Not open right now.",
  },
  hospital: {
    open: "Accepting patients.",
    busy: "Limited service or long waits.",
    full: "Not accepting new patients.",
    closed: "Not open right now.",
  },
  clinic: {
    open: "Accepting patients.",
    busy: "Limited service or long waits.",
    full: "Not accepting new patients.",
    closed: "Not open right now.",
  },
};

export function statusHint(type: FacilityType, value: StatusValue): string {
  return STATUS_HINT[type][value] ?? "";
}

// "Temporary evacuation center" when the center was added through the app and has a
// center_type; otherwise the plain type label ("Hospital", "Clinic", "Evacuation center").
export function facilityKindLabel(f: Facility): string {
  if (f.type === "evacuation_center" && f.center_type) {
    return `${f.center_type === "temporary" ? "Temporary" : "Permanent"} evacuation center`;
  }
  return TYPE_LABEL[f.type];
}