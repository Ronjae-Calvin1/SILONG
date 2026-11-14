import { useEffect, useState } from "react";
import type { Facility } from "../types";
import { distanceKm, formatKm } from "./geo";
import { STATUS_SYMBOL, facilityKindLabel, statusHint, statusKey, timeAgo } from "./statusInfo";

const SHORT_STATUS = {
  open: "Open",
  almost_full: "Almost full",
  busy: "Busy",
  full: "Full",
  closed: "Closed",
  unknown: "No status",
} as const;

interface Props {
  facilities: Facility[]; // already filtered by the chips
  origin: { lat: number; lng: number }; // the user, or the city center when location is unknown
  hasUserLocation: boolean;
  selectedId: number | null;
  onSelect: (facility: Facility) => void;
}

// Current time, refreshed every minute so "15 minutes ago" stays correct.
function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

export function FacilityList({ facilities, origin, hasUserLocation, selectedId, onSelect }: Props) {
  const now = useNow();

  const rows = facilities
    .map((f) => ({ f, km: distanceKm(origin.lat, origin.lng, f.latitude, f.longitude) }))
    .sort((a, b) => a.km - b.km);

  // When a pin is tapped on the map, bring its row into view.
  useEffect(() => {
    if (selectedId === null) return;
    document.getElementById(`facility-item-${selectedId}`)?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  return (
    <section className="facility-list" aria-label="Places on the map">
      <div className="facility-list-head">
        <p className="facility-list-count" aria-live="polite">
          {rows.length} {rows.length === 1 ? "place" : "places"} on the map
        </p>
        <span className="facility-list-sort">Nearest first</span>
      </div>
      {!hasUserLocation && (
        <p className="facility-list-hint">Sorted from the city center. Press the ◎ button on the map to use your location.</p>
      )}

      {rows.length === 0 ? (
        <p className="facility-list-empty">No places match. Try another filter.</p>
      ) : (
        <ul className="facility-list-items">
          {rows.map(({ f, km }) => {
            const key = statusKey(f);
            const s = f.status;
            let detail: string;
            if (f.type === "evacuation_center" && f.people_inside !== null && f.max_capacity !== null) {
              detail = `${f.people_inside} of ${f.max_capacity} people`;
            } else if (s) {
              detail = statusHint(f.type, s.status);
            } else {
              detail = "Nobody has reported yet";
            }
            const ago = s ? ` · ${timeAgo(s.updated_at, now)}` : "";
            return (
              <li key={f.id}>
                <button
                  type="button"
                  id={`facility-item-${f.id}`}
                  className="facility-item"
                  aria-current={f.id === selectedId ? "true" : undefined}
                  onClick={() => onSelect(f)}
                >
                  <span className="facility-item-top">
                    <span className="facility-item-name">{f.name}</span>
                    <span className="fp-badge" data-status={key} data-outdated={f.is_outdated ? "true" : "false"}>
                      <span className="fp-badge-symbol" aria-hidden="true">
                        {STATUS_SYMBOL[key]}
                      </span>
                      {SHORT_STATUS[key]}
                    </span>
                  </span>
                  <span className="facility-item-meta">
                    {facilityKindLabel(f)}
                    {hasUserLocation ? ` · ${formatKm(km)}` : ""}
                  </span>
                  <span className="facility-item-meta">
                    {detail}
                    {ago}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}