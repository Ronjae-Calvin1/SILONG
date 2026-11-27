import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Place } from "../api/types";
import LiveMap, { type Layers } from "./LiveMap";
import ReportActions from "./ReportActions";
import ReportCard from "./ReportCard";
import ReportDetails from "./ReportDetails";
import { placeText, reportTitle } from "./format";
import { useReports, type Filter } from "./useReports";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "new", label: "New" },
  { id: "handling", label: "Being handled" },
  { id: "resolved", label: "Resolved" },
];
const LAYER_LABELS: { id: keyof Layers; label: string }[] = [
  { id: "reports", label: "Reports" },
  { id: "places", label: "Places" },
  { id: "hazards", label: "Hazards" },
  { id: "resolved", label: "Resolved" },
];

export default function LiveMapPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [layers, setLayers] = useState<Layers>({ reports: true, hazards: true, places: true, resolved: true });
  const [places, setPlaces] = useState<Place[]>([]);
  const { items, loaded, summary, newHelp, hasNewHelp, error, apply, refresh } = useReports(filter, null);

  // Approved places: for the map layer and for the nearest name on a report. Public call, once.
  useEffect(() => {
    api.getPlaces().then(setPlaces).catch(() => undefined);
  }, []);

  const counts = useMemo(
    () => ({
      all: summary ? summary.new_reports + summary.being_handled : null,
      new: summary?.new_reports ?? null,
      handling: summary?.being_handled ?? null,
    }),
    [summary],
  );

  function openAlert() {
    if (!newHelp) return;
    setFilter("all");
    setSelectedId(newHelp.id);
  }

  return (
    <div className="live">
      <aside className="live-list">
        <div className="chip-row" role="group" aria-label="Filter reports">
          {FILTERS.map((f) => {
            const n = f.id === "all" ? counts.all : f.id === "new" ? counts.new : f.id === "handling" ? counts.handling : null;
            return (
              <button key={f.id} className={f.id === filter ? "pill pill-on" : "pill"} aria-pressed={f.id === filter} onClick={() => setFilter(f.id)}>
                {f.label}
                {n !== null ? ` ${n}` : ""}
              </button>
            );
          })}
        </div>
        <p className="live-sub">Most urgent first · refreshes every 10 s</p>

        {hasNewHelp && (
          <div className="alert-red" role="alert">
            <div>
              <strong>Needs help</strong>
              <span>{newHelp ? `${reportTitle(newHelp)} · ${placeText(newHelp, places)}` : "A new help request is waiting."}</span>
            </div>
            {newHelp && (
              <button className="btn btn-white" onClick={openAlert}>
                Open
              </button>
            )}
          </div>
        )}
        {error && (
          <div className="notice-error" role="alert">
            {error.detail}{" "}
            <button className="link-btn" onClick={refresh}>
              Try again
            </button>
          </div>
        )}

        <div className="cards">
          {items.map((r) => (
            <ReportCard key={r.id} report={r} places={places} selected={r.id === selectedId} onSelect={() => setSelectedId(r.id === selectedId ? null : r.id)}>
              <div className="card-body">
                <ReportDetails r={r} places={places} />
                <ReportActions report={r} onDone={apply} onStale={refresh} />
              </div>
            </ReportCard>
          ))}
          {loaded && items.length === 0 && !error && <p className="empty">No reports here right now.</p>}
          {!loaded && !error && <p className="empty">Loading…</p>}
        </div>
      </aside>

      <section className="live-map">
        <div className="layer-row" role="group" aria-label="Map layers">
          {LAYER_LABELS.map((l) => (
            <button key={l.id} className={layers[l.id] ? "pill pill-dark" : "pill"} aria-pressed={layers[l.id]} onClick={() => setLayers((s) => ({ ...s, [l.id]: !s[l.id] }))}>
              {l.label}
            </button>
          ))}
        </div>
        <LiveMap reports={items} places={places} layers={layers} selectedId={selectedId} onSelect={setSelectedId} />
      </section>
    </div>
  );
}
