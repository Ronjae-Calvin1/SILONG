// Data and helpers for the Emergency Hotlines panel.
// National numbers are fixed (from the design). Local numbers are NOT typed here:
// they are read from the facilities the map already loads from the backend.

import type { Facility, FacilityType } from "../types";
import { TYPE_LABEL, phoneLinks } from "./statusInfo";

export type HotlineCategory = "all" | "medical" | "accident" | "flood" | "violence" | "missing";

export const CATEGORIES: { id: HotlineCategory; label: string }[] = [
  { id: "all", label: "All" },
  { id: "medical", label: "Medical" },
  { id: "accident", label: "Accident" },
  { id: "flood", label: "Flood" },
  { id: "violence", label: "Violence" },
  { id: "missing", label: "Missing person" },
];

// Shown at the top of the panel no matter which category is selected.
export const NATIONAL_HOTLINES = [
  { number: "911", name: "National Emergency" },
  { number: "143", name: "Philippine Red Cross" },
];

// Which emergency categories each facility type can answer.
// Only the sure match is listed. Add more lines here only when you are sure.
const CATEGORIES_BY_TYPE: Partial<Record<FacilityType, HotlineCategory[]>> = {
  hospital: ["medical"],
  clinic: ["medical"],
};

export interface LocalHotline {
  id: string;
  name: string;
  description: string;
  tag: string; // small label on the card, e.g. "Medical"
  categories: HotlineCategory[];
  phones: { text: string; href: string }[];
}

// Turns the loaded facilities into hotline cards. A facility with no usable
// phone number (missing or "N/A") is left out, so we never show a dead Call button.
export function buildLocalHotlines(facilities: Facility[]): LocalHotline[] {
  const list: LocalHotline[] = [];
  facilities.forEach((f) => {
    const categories = CATEGORIES_BY_TYPE[f.type];
    const phones = phoneLinks(f.contact);
    if (!categories || phones.length === 0) return;
    list.push({
      id: `facility-${f.id}`,
      name: f.name,
      description: f.address ? `${TYPE_LABEL[f.type]} · ${f.address}` : TYPE_LABEL[f.type],
      tag: CATEGORIES.find((c) => c.id === categories[0])?.label ?? "",
      categories,
      phones,
    });
  });
  return list;
}