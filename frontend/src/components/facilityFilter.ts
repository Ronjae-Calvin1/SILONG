import type { Facility } from "../types";

export type FilterId = "all" | "hospital" | "clinic" | "temporary" | "permanent";

// Order here = order of the chips on screen.
export const FILTERS: { id: FilterId; label: string }[] = [
  { id: "all", label: "All" },
  { id: "hospital", label: "Hospitals" },
  { id: "clinic", label: "Clinics" },
  { id: "temporary", label: "Temporary" },
  { id: "permanent", label: "Permanent" },
];

// Should this facility's pin be shown for the chosen chip?
// Only centers added through the app have a center_type, so an evacuation
// center that is not marked "temporary" is treated as permanent.
export function matchesFilter(f: Facility, filter: FilterId): boolean {
  switch (filter) {
    case "hospital":
      return f.type === "hospital";
    case "clinic":
      return f.type === "clinic";
    case "temporary":
      return f.type === "evacuation_center" && f.center_type === "temporary";
    case "permanent":
      return f.type === "evacuation_center" && f.center_type !== "temporary";
    default:
      return true;
  }
}

// Short label for search results.
export function typeLabel(f: Facility): string {
  if (f.type === "hospital") return "Hospital";
  if (f.type === "clinic") return "Clinic";
  return f.center_type === "temporary" ? "Temporary evacuation center" : "Evacuation center";
}