// "Hidden on this phone": evacuation centers this person hid on this browser only.
// Nothing is sent to the server, so other people (and other phones) still see the center.
// Clearing the browser's site data clears this list, and the centers show again.

import type { Facility } from "../types";
import { facilityKindLabel } from "./statusInfo";

const KEY = "silong:hidden-centers";

export interface HiddenCenter {
  id: number;
  name: string;
  kind: string; // "Temporary evacuation center", "Permanent evacuation center" or "Evacuation center"
}

export function loadHidden(): HiddenCenter[] {
  try {
    const raw = localStorage.getItem(KEY);
    const list: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(list)) return [];
    return list.filter(
      (x): x is HiddenCenter =>
        !!x && typeof x.id === "number" && typeof x.name === "string" && typeof x.kind === "string",
    );
  } catch {
    return []; // storage blocked or the saved text is damaged: start with an empty list
  }
}

// Returns false when the browser could not save (private mode, storage full); the caller still
// hides the pin for this visit, but should tell the person it will not be remembered.
export function saveHidden(list: HiddenCenter[]): boolean {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
    return true;
  } catch {
    return false;
  }
}

// Only evacuation centers can be hidden. Hospitals and clinics never are.
export function toHiddenCenter(f: Facility): HiddenCenter | null {
  if (f.type !== "evacuation_center") return null;
  return { id: f.id, name: f.name, kind: facilityKindLabel(f) };
}
