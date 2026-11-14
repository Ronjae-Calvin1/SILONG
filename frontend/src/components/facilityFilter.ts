import type { Facility } from "../types";
import type { IconName } from "./icons";
export type FilterId = "all" | "hospital" | "clinic" | "temporary" | "permanent";

export const FILTERS: { id: FilterId; label: string; icon: IconName }[] = [
  { id: "all", label: "All", icon: "all" },
  { id: "hospital", label: "Hospitals", icon: "hospital" },
  { id: "clinic", label: "Clinics", icon: "clinic" },
  { id: "temporary", label: "Temporary", icon: "tent" },
  { id: "permanent", label: "Permanent", icon: "house" },
];

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