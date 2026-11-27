import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AdminReport, ReportQuery, Summary } from "../api/types";
import { isOpen } from "./format";

// Desktop: all, new, handling, resolved. Phone: new, mine, handling, resolved.
export type Filter = "all" | "new" | "handling" | "resolved" | "mine";

// "All" sends no status at all: open reports only, as decided.
function queryFor(f: Filter): ReportQuery {
  if (f === "new") return { status: "new" };
  if (f === "handling") return { status: "handling" };
  if (f === "resolved") return { status: "resolved" };
  if (f === "mine") return { status: "handling", mine: true };
  return {};
}

// Does an item belong in this filter's list? Used to drop items that changed out of it.
export function matches(f: Filter, r: AdminReport): boolean {
  if (f === "new") return r.status === "new";
  if (f === "handling") return r.status === "being_handled";
  if (f === "mine") return r.status === "being_handled" && r.is_mine;
  if (f === "resolved") return r.status === "resolved" || r.status === "false";
  return isOpen(r);
}

// The server's documented order: new help (longest waiting first), other open (longest waiting first), closed (newest first).
function rank(r: AdminReport): number {
  if (r.is_new_help) return 0;
  return isOpen(r) ? 1 : 2;
}
function sortLikeServer(list: AdminReport[]): AdminReport[] {
  return [...list].sort((a, b) => {
    const ra = rank(a);
    const rb = rank(b);
    if (ra !== rb) return ra - rb;
    if (ra === 2) return b.updated_at.localeCompare(a.updated_at);
    return a.created_at.localeCompare(b.created_at);
  });
}

export function mergeReports(prev: AdminReport[], changed: AdminReport[], f: Filter): AdminReport[] {
  const byId = new Map(prev.map((r) => [r.id, r]));
  for (const r of changed) {
    if (matches(f, r)) byId.set(r.id, r);
    else byId.delete(r.id);
  }
  return sortLikeServer([...byId.values()]);
}

// Tested against the backend: with `status=new` (or handling, or mine) the `since` answer leaves out an item that moved
// out of that status (taken by another Admin, resolved...), so it would stay on screen. Only the unfiltered list
// (open reports) and Resolved are merged with `since`; the other filters read the whole (small) list every poll.
const SINCE_FILTERS: Filter[] = ["all", "resolved"];
const FULL_REFRESH_EVERY = 6; // polls: even with `since`, read the whole list now and then

interface Data {
  filter: Filter;
  items: AdminReport[];
  serverTime: string | null;
}

export function useReports(filter: Filter, position: { latitude: number; longitude: number } | null) {
  const [data, setData] = useState<Data | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [hasNewHelp, setHasNewHelp] = useState(false);
  const [newHelp, setNewHelp] = useState<AdminReport | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [reload, setReload] = useState(0);
  const lat = position?.latitude;
  const lng = position?.longitude;

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let since: string | null = null;
    let polls = 0;

    const run = async () => {
      try {
        const full = since === null || !SINCE_FILTERS.includes(filter) || polls % FULL_REFRESH_EVERY === 0;
        const query: ReportQuery = { ...queryFor(filter) };
        if (lat !== undefined && lng !== undefined) {
          query.latitude = lat;
          query.longitude = lng;
        }
        if (!full && since) query.since = since;
        const [answer, sum] = await Promise.all([api.getReports(query), api.getSummary()]);
        if (cancelled) return;
        polls += 1;
        since = answer.server_time;
        setData((prev) => ({
          filter,
          serverTime: answer.server_time,
          items: full || !prev || prev.filter !== filter ? answer.items : mergeReports(prev.items, answer.items, filter),
        }));
        setSummary(sum);
        setHasNewHelp(answer.has_new_help);
        setError(null);

        // The alert needs the newest New help request even when this filter does not list it.
        if (answer.has_new_help) {
          let list = answer.items.filter((r) => r.is_new_help);
          if (list.length === 0 && filter !== "all" && filter !== "new") {
            list = (await api.getReports({ status: "new" })).items.filter((r) => r.is_new_help);
          }
          if (!cancelled) setNewHelp(list.sort((a, b) => b.id - a.id)[0] ?? null);
        } else {
          setNewHelp(null);
        }
        timer = window.setTimeout(run, Math.max(2, answer.refresh_seconds) * 1000);
      } catch (e) {
        if (cancelled) return;
        const err = e instanceof ApiError ? e : new ApiError(0, "Can't connect. Check your connection and try again.");
        setError(err);
        // 401 or 403: the session is over and the whole console is replaced, so polling stops here.
        if (err.status === 401 || err.status === 403) return;
        timer = window.setTimeout(run, 10_000);
      }
    };
    run();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [filter, lat, lng, reload]);

  // After an action: show the answer at once, then poll again.
  const apply = useCallback(
    (item: AdminReport) => {
      setData((prev) => (prev ? { ...prev, items: mergeReports(prev.items, [item], filter) } : prev));
      setReload((n) => n + 1);
    },
    [filter],
  );
  const refresh = useCallback(() => setReload((n) => n + 1), []);

  const current = data && data.filter === filter ? data : null;
  return {
    items: current?.items ?? [],
    loaded: current !== null,
    serverTime: current?.serverTime ?? null,
    summary,
    hasNewHelp,
    newHelp,
    error,
    apply,
    refresh,
  };
}
