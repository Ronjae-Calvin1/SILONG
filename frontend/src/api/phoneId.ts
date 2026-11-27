// Anonymous phone ID. One random value per browser, made once and kept in localStorage.
// The server stores only a hash of it. It is not proof of who someone is, and clearing the
// browser data makes a new one. It is sent as the X-Phone-Id header (see client.ts) and is
// never shown, logged or put in a URL.

const KEY = "silong:phone-id";

// Server rule (docs/API.md, "Phone ID"): 16 to 64 letters, digits, "-" or "_".
const VALID = /^[A-Za-z0-9_-]{16,64}$/;

let cached: string | null = null;

function makeId(): string {
  // randomUUID only exists on secure pages (https or localhost), so fall back to random bytes.
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function getPhoneId(): string {
  if (cached) return cached;
  let id: string | null = null;
  try {
    id = localStorage.getItem(KEY);
  } catch {
    // Storage blocked: the ID then lives only until the page is closed.
  }
  if (!id || !VALID.test(id)) {
    id = makeId();
    try {
      localStorage.setItem(KEY, id);
    } catch {
      // Same as above.
    }
  }
  cached = id;
  return id;
}
