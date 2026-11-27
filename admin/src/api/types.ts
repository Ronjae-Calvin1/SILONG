// Shapes of the admin answers this part uses (see docs/API.md).

export interface AdminUser {
  id: number;
  name: string;
  role: string; // always "admin": never branch on it, never show it
  idle_timeout_minutes: number;
}

export interface SignInAnswer {
  token: string;
  token_type: string;
  user: AdminUser;
}

export type ReportKind = "help" | "hazard";
export type ReportStatus = "new" | "being_handled" | "resolved" | "false";
export type HazardState = "pending" | "unconfirmed" | "verified";

export interface AdminReport {
  id: number;
  kind: ReportKind;
  status: ReportStatus;
  is_new_help: boolean;
  category: string | null;
  categories: string[];
  people: number | null;
  can_move: "yes" | "no" | "unsure" | null;
  latitude: number;
  longitude: number;
  contacts: string[];
  notes: string[];
  created_at: string;
  updated_at: string;
  taken_by: string | null;
  is_mine: boolean;
  distance_m: number | null;
  closed_by: string | null;
  resolution_note: string | null;
  false_reason: string | null;
  verified: boolean;
  verified_by: string | null;
  hazard_state: HazardState | null;
  phones: number;
  report_count: number;
}

export interface ReportsAnswer {
  server_time: string;
  refresh_seconds: number;
  new_help_count: number;
  has_new_help: boolean;
  latest_report_id: number | null;
  since: string | null;
  items: AdminReport[];
}

export interface Summary {
  new_reports: number;
  being_handled: number;
  mine: number;
  pending_places: number;
  removed_centers: number;
  server_time: string;
}

export interface ContactSettings {
  control_room_number: string | null;
  support_email: string | null;
  support_number: string | null;
}

// Only what the Live map needs from GET /api/facilities.
export interface Place {
  id: number;
  name: string;
  type: string;
  latitude: number;
  longitude: number;
}

export interface ReportQuery {
  status?: "new" | "handling" | "resolved";
  mine?: boolean;
  since?: string;
  latitude?: number;
  longitude?: number;
}
