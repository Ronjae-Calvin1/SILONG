// Single place that knows how to reach the backend. Every call goes through request().
// Public calls only: the map, status updates, adding a place, sending a report, and the chat. No Admin route is called from the user site.

import type {
  Facility,
  FacilityStatus,
  MyReportItem,
  NewEvacuationCenter,
  NewReport,
  ReportSent,
  SiloAnswer,
  StatusPayload,
} from "../types";
import { getPhoneId } from "./phoneId";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";

// What a screen gets when a call fails: the HTTP status (0 = the server could not be reached)
// and the server's `detail` text, which is safe to show as it is. `message` is the same text.
export class ApiError extends Error {
  status: number;
  detail: string;
  retryAfter?: number; // seconds, for 429. The browser may not be allowed to read the header, so it can be empty.
  constructor(status: number, detail: string, retryAfter?: number) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
  }
}

// Used only when the server sent no `detail` at all (for example an error from a proxy).
const FALLBACK_DETAIL: Record<number, string> = {
  400: "The request was not accepted. Please try again.",
  401: "You are not signed in.",
  403: "This is not allowed.",
  404: "Not found.",
  409: "This clashes with what is already saved.",
  422: "Some of the information was not accepted.",
  423: "This account is locked.",
  429: "Too many requests. Please wait a moment and try again.",
};

// FastAPI sends `detail` as a string (our own errors) or as a list (shape errors, 422).
function messageFromBody(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    const field = first.loc && first.loc.length > 1 ? String(first.loc[first.loc.length - 1]) : "";
    const msg = (first.msg ?? fallback).replace(/^Value error, /, "");
    return field ? `${field.replace(/_/g, " ")}: ${msg}` : msg;
  }
  return fallback;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown; // sent as JSON
  phone?: boolean; // add the X-Phone-Id header (the calls listed in docs/FRONTEND_TODO.md 3.1)
}

async function request<T>(path: string, { method = "GET", body, phone = false }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (phone) headers["X-Phone-Id"] = getPhoneId();

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your internet connection and try again.");
  }

  if (!res.ok) {
    const json = await res.json().catch(() => null);
    const fallback = FALLBACK_DETAIL[res.status] ?? `Something went wrong (error ${res.status}).`;
    const wait = Number.parseInt(res.headers.get("Retry-After") ?? "", 10);
    throw new ApiError(res.status, messageFromBody(json, fallback), Number.isFinite(wait) ? wait : undefined);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  getFacilities: () => request<Facility[]>("/facilities", { phone: true }),
  // Returns the new latest status for that facility.
  submitStatus: (facilityId: number, payload: StatusPayload) =>
    request<FacilityStatus>(`/facilities/${facilityId}/status`, { method: "POST", body: payload, phone: true }),
  // Returns the new center, shaped like an item of getFacilities().
  addEvacuationCenter: (payload: NewEvacuationCenter) =>
    request<Facility>("/evacuation-centers", { method: "POST", body: payload, phone: true }),
  // Sends a help request or a hazard report. Needs X-Phone-Id (400 without it).
  sendReport: (payload: NewReport) => request<ReportSent>("/reports", { method: "POST", body: payload, phone: true }),
  // This phone's own reports, newest first.
  getMyReports: () => request<MyReportItem[]>("/reports/mine", { phone: true }),
  // Silo, the chatbot: one question in, one short answer out. Nothing is kept between questions.
  askSilo: (question: string) => request<SiloAnswer>("/chat", { method: "POST", body: { question } }),
};
