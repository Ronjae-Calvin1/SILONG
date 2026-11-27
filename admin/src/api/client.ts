// Single place that knows how to reach the backend. Every call goes through request().
// The token lives in sessionStorage of this site only, and goes only in the Authorization header.

import type {
  AdminReport,
  AdminUser,
  ContactSettings,
  Place,
  ReportQuery,
  ReportsAnswer,
  SignInAnswer,
  Summary,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";
const TOKEN_KEY = "silong_admin_token";

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: the sign-in then only lasts until the page reloads */
  }
}

// status 0 = the server could not be reached. `detail` is the server's text, shown as written.
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

// Called once when an admin call is answered with 401 or 403 while a token is held.
let onSignedOut: ((detail: string) => void) | null = null;
export function setSignedOutHandler(fn: ((detail: string) => void) | null): void {
  onSignedOut = fn;
}

// Used only when the server sent no `detail` (for example an error from a proxy).
const FALLBACK_DETAIL: Record<number, string> = {
  401: "You are not signed in.",
  403: "This is not allowed.",
  404: "Not found.",
  409: "This clashes with what is already saved.",
  422: "Some of the information was not accepted.",
  423: "This account is locked.",
  429: "Too many requests. Please wait a moment and try again.",
};

// `detail` is a string (our own errors) or a list (shape errors, 422): show the first message.
function messageFromBody(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    return (first.msg ?? fallback).replace(/^Value error, /, "");
  }
  return fallback;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown; // sent as JSON
  auth?: boolean; // add the Authorization header (default true)
  // A 401 or 403 on this call means "wrong password" or similar, not "you were signed out".
  keepSession?: boolean;
}

async function request<T>(path: string, { method = "GET", body, auth = true, keepSession = false }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = auth ? getToken() : null;
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Can't connect. SILONG needs the internet. Check your connection and try again.");
  }

  if (!res.ok) {
    const json = await res.json().catch(() => null);
    const fallback = FALLBACK_DETAIL[res.status] ?? `Something went wrong (error ${res.status}).`;
    const detail = messageFromBody(json, fallback);
    if (token && !keepSession && (res.status === 401 || res.status === 403)) {
      setToken(null);
      onSignedOut?.(detail);
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function queryString(q: ReportQuery): string {
  const p = new URLSearchParams();
  if (q.status) p.set("status", q.status);
  if (q.mine) p.set("mine", "true");
  if (q.since) p.set("since", q.since);
  if (q.latitude !== undefined && q.longitude !== undefined) {
    p.set("latitude", String(q.latitude));
    p.set("longitude", String(q.longitude));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  signIn: (name: string, password: string) =>
    request<SignInAnswer>("/auth/sign-in", { method: "POST", body: { name, password }, auth: false }),
  signOut: () => request<{ message: string }>("/auth/sign-out", { method: "POST", keepSession: true }),
  me: () => request<AdminUser>("/me"),

  getReports: (q: ReportQuery = {}) => request<ReportsAnswer>(`/admin/reports${queryString(q)}`),
  getSummary: () => request<Summary>("/admin/summary"),
  // Approved places only; public, so no token is sent.
  getPlaces: () => request<Place[]>("/facilities", { auth: false }),
  getContactSettings: () => request<ContactSettings>("/admin/contact-settings"),

  // Every action answers with the changed report, shaped like a list item.
  take: (id: number) => request<AdminReport>(`/admin/reports/${id}/take`, { method: "POST" }),
  release: (id: number) => request<AdminReport>(`/admin/reports/${id}/release`, { method: "POST" }),
  resolve: (id: number, whatWasDone: string) =>
    request<AdminReport>(`/admin/reports/${id}/resolve`, { method: "POST", body: { what_was_done: whatWasDone } }),
  markFalse: (id: number, reason: string) =>
    request<AdminReport>(`/admin/reports/${id}/mark-false`, { method: "POST", body: { reason } }),
  verify: (id: number) => request<AdminReport>(`/admin/reports/${id}/verify`, { method: "POST" }),
};

// A 429's wait time cannot be read from the Retry-After header in a browser, so read it from the text.
export function waitSeconds(detail: string): number | null {
  const m = /(\d+)\s*(minute|second)/i.exec(detail);
  if (!m) return null;
  return Number(m[1]) * (m[2].toLowerCase() === "minute" ? 60 : 1);
}
