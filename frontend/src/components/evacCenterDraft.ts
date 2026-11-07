// What someone has typed into the "Add evacuation center" form so far.
// Kept by AddEvacCenter, so it survives going back to the map to move the pin.

import type { CenterType } from "../types";

export interface CenterDraft {
  name: string;
  centerType: CenterType | null;
  barangay: string;
  address: string;
  contact: string;
  capacity: string; // text while typing; checked and turned into a number on submit
  note: string;
}

export const EMPTY_DRAFT: CenterDraft = {
  name: "",
  centerType: null,
  barangay: "",
  address: "",
  contact: "",
  capacity: "",
  note: "",
};
