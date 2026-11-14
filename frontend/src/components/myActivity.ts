// What this phone remembers about the person's own activity (no accounts, so it is all local):
// reports sent from the incident form, and evacuation centers added from this phone.

export const REPORTS_KEY = "typhoon-prep:incident-reports"; // written by IncidentPanel
const PLACES_KEY = "silong:my-places"; // written when an evacuation center is added here

export interface MyReport {
  mode: "help" | "hazard";
  kind: string;
  details: string;
  savedAt: string; // ISO time
}

export interface MyPlace {
  id: number;
  name: string;
  kind: string;
  savedAt: string; // ISO time
}

function readList(key: string): unknown[] {
  try {
    const raw = localStorage.getItem(key);
    const list: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

// Newest first.
export function loadMyReports(): MyReport[] {
  return readList(REPORTS_KEY)
    .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
    .map((x) => ({
      mode: x.mode === "help" ? ("help" as const) : ("hazard" as const),
      kind: typeof x.kind === "string" ? x.kind : "",
      details: typeof x.details === "string" ? x.details : "",
      savedAt: typeof x.savedAt === "string" ? x.savedAt : "",
    }))
    .reverse();
}

export function loadMyPlaces(): MyPlace[] {
  return readList(PLACES_KEY)
    .filter(
      (x): x is MyPlace =>
        !!x && typeof (x as MyPlace).id === "number" && typeof (x as MyPlace).name === "string",
    )
    .reverse();
}

export function rememberMyPlace(place: MyPlace): void {
  try {
    const list = readList(PLACES_KEY).filter((x) => (x as MyPlace).id !== place.id);
    list.push(place);
    localStorage.setItem(PLACES_KEY, JSON.stringify(list));
  } catch {
    // Storage may be blocked. The center is still added; it just is not listed under "My suggested places".
  }
}
