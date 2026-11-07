// Backbone: map slice + capacity/availability status.

export type FacilityType = "hospital" | "clinic" | "evacuation_center";

export type CenterType = "permanent" | "temporary";

export type StatusValue = "open" | "almost_full" | "busy" | "full" | "closed";

export type ResourceName = "space" | "food" | "water" | "power" | "toilets" | "medical";

// Latest capacity/availability report for a facility (from the backend).
export interface FacilityStatus {
  id: number;
  status: StatusValue;
  people_inside: number | null;
  max_capacity: number | null;
  resources: ResourceName[];
  note: string | null;
  updated_at: string; // ISO time, UTC
  is_outdated: boolean; // decided by the server (one 6h setting lives there)
}

export interface Facility {
  id: number;
  key: string | null; // stable identity from the data source: "osm:way/1", "manual:...", "user:3"
  name: string;
  type: FacilityType;
  latitude: number;
  longitude: number;
  address?: string;
  contact?: string;
  notes?: string;
  source: string; // "osm" | "manual" | "user"
  center_type?: CenterType | null; // only for centers added through the app
  status: FacilityStatus | null; // null = "No status yet"
  // Capacity fields: evacuation centers only. null = not known (or not an evacuation center).
  people_inside: number | null;
  max_capacity: number | null;
  spaces_left: number | null;
  percent_full: number | null; // can pass 100 when a center is over capacity
  is_outdated: boolean | null; // same as status.is_outdated; null when there is no status
}

// What the "Update status" form sends.
export interface StatusPayload {
  status: StatusValue;
  people_inside?: number;
  max_capacity?: number;
  resources?: ResourceName[];
  note?: string;
}

// What the "Add evacuation center" form sends. The backend accepts nothing else.
export interface NewEvacuationCenter {
  name: string;
  center_type: CenterType;
  barangay?: string;
  address?: string;
  contact?: string;
  max_capacity: number;
  latitude: number;
  longitude: number;
  note?: string;
}

// What the backend answers after a removal (the center is hidden, not deleted).
export interface RemovedCenter {
  id: number;
  key: string;
  name: string;
  removed_at: string; // ISO time, UTC
  message: string | null;
}
