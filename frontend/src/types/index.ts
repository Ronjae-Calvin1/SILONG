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
  source: string; // "user" | "official"
  source_label: string; // shown as it is: "Reported by a user" or "Confirmed by official"
  // Only on the answer to a new report, when the server changed what was sent
  // (for example it saved "full" because people_inside reached max_capacity).
  message?: string | null;
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
  // "pending" = added from this phone and waiting for an Admin. Only this phone gets it back from the server.
  // Anything else (or missing) = on the map for everyone.
  approval_status?: "pending" | "approved" | string;
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

// One answer from the SILONG chatbot (Silo). `topic` is the checked-guide entry the answer came from,
// or null when nothing in the guide matched (then `answer` is the fixed "I don't have that info" line).
export interface SiloAnswer {
  answer: string;
  topic: string | null;
}

// ---------- Incident reports (POST /api/reports, GET /api/reports/mine) ----------

export type ReportKind = "help" | "hazard";

// new = waiting, being_handled = an Admin took it, resolved = closed.
export type ReportStatus = "new" | "being_handled" | "resolved";

// What the incident form sends. The server refuses any other field, and refuses
// `people` and `can_move` on a hazard.
export interface NewReport {
  kind: ReportKind;
  category: string; // 1 to 40 characters
  latitude: number;
  longitude: number;
  note?: string; // up to 140 characters
  contact?: string; // help only, required there, up to 60 characters
  people?: number; // help only
  can_move?: "yes" | "no" | "unsure"; // help only
}

// The answer to a new report.
export interface ReportSent {
  id: number;
  kind: ReportKind;
  status: ReportStatus;
  label: string; // "New", "Being handled" or "Resolved"
  created_at: string; // ISO time, UTC
  message: string;
}

// One item of this phone's own reports.
export interface MyReportItem {
  id: number;
  kind: ReportKind;
  status: ReportStatus;
  label: string;
  category: string | null;
  latitude: number;
  longitude: number;
  note: string | null;
  created_at: string;
  updated_at: string;
}
