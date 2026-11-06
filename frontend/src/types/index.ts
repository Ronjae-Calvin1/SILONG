// Backbone: map slice + capacity/availability status.

export type FacilityType = "hospital" | "clinic" | "evacuation_center";

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
  name: string;
  type: FacilityType;
  latitude: number;
  longitude: number;
  address?: string;
  contact?: string;
  notes?: string;
  status: FacilityStatus | null; // null = "No status yet"
}

// What the "Update status" form sends.
export interface StatusPayload {
  status: StatusValue;
  people_inside?: number;
  max_capacity?: number;
  resources?: ResourceName[];
  note?: string;
}
