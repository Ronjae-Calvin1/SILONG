// Small helpers for values that come from the server.

// The server sends times as ISO strings in UTC. A string with no zone mark would be read as
// local time by the browser, so one is added when it is missing.
export function parseApiTime(iso: string): Date {
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso);
  return new Date(hasZone ? iso : `${iso}Z`);
}

// Ids are numbers in the API, but some screens keep them as strings (advisories, warnings,
// updates). Use this instead of writing String(id) in each screen.
export function idToString(id: number | string): string {
  return String(id);
}
