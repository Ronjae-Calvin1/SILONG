import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Facility } from "../types";
import { Icon } from "./icons";
import {
  RESOURCE_OPTIONS,
  TYPE_LABEL,
  clockTime,
  phoneLinks,
  statusKey,
  statusLabel,
  timeAgo,
} from "./statusInfo";
import "./StatusPanel.css";
import "./EvacManager.css";

// Current time, refreshed every minute (and when the tab comes back), so the
// "15 minutes ago" labels never go stale while the page stays open.
function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const id = window.setInterval(tick, 60_000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, []);
  return now;
}

interface Props {
  facility: Facility;
  onClose: () => void;
  onUpdateStatus: () => void;
  onRemoved: (facilityId: number) => void; // the server hid the center; the page removes its pin
}

// Details for the tapped pin: info, current status, and the "Update status" button.
// Evacuation centers also get "Remove from map" (with a confirmation step).
export function FacilityPanel({ facility: f, onClose, onUpdateStatus, onRemoved }: Props) {
  const now = useNow();
  const [confirming, setConfirming] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const confirmRef = useRef<HTMLDivElement>(null);

  // The confirmation appears at the bottom of a scrolling panel: scroll the panel
  // (only the panel, not the page behind it) down so it is seen.
  useEffect(() => {
    const panel = confirmRef.current?.parentElement;
    if (confirming && panel) panel.scrollTop = panel.scrollHeight;
  }, [confirming]);

  async function remove() {
    if (removing) return;
    setRemoving(true);
    setRemoveError(null);
    try {
      await api.removeEvacuationCenter(f.id);
      onRemoved(f.id); // parent hides the pin and closes this panel
    } catch (err) {
      setRemoveError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setRemoving(false);
    }
  }

  const s = f.status;
  const phones = phoneLinks(f.contact);
  const resourceText = s
    ? RESOURCE_OPTIONS.filter((r) => s.resources.includes(r.value))
        .map((r) => r.label)
        .join(", ")
    : "";

  return (
    <section className="facility-panel" aria-label={`${f.name} details`}>
      <button className="panel-close" onClick={onClose} aria-label="Close details">
        <Icon name="close" />
      </button>

      <h2 className="facility-name">{f.name}</h2>
      <p className="facility-type">{TYPE_LABEL[f.type]}</p>
      {f.address && <p className="facility-line">{f.address}</p>}
      {phones.map((p) => (
        <p className="facility-line" key={p.href + p.text}>
          <a href={p.href}>{p.text}</a>
        </p>
      ))}

      <div className="status-block">
        <span className="status-badge" data-status={statusKey(f)} data-outdated={s?.is_outdated ? "true" : "false"}>
          {statusLabel(f)}
        </span>
        {s?.is_outdated && <span className="outdated-badge">May be outdated</span>}

        {s ? (
          <>
            <p className="facility-line">
              Last updated: {clockTime(s.updated_at, now)} ({timeAgo(s.updated_at, now)})
            </p>
            {s.people_inside !== null && (
              <p className="facility-line">
                People inside: {s.people_inside}
                {s.max_capacity !== null ? ` / ${s.max_capacity}` : ""}
              </p>
            )}
            {s.people_inside === null && s.max_capacity !== null && (
              <p className="facility-line">Capacity: {s.max_capacity}</p>
            )}
            {resourceText && <p className="facility-line">Available: {resourceText}</p>}
            {s.note && <p className="facility-line facility-note">“{s.note}”</p>}
          </>
        ) : (
          <p className="facility-line">Nobody has reported yet. Be the first to update.</p>
        )}
      </div>

      <button className="update-status-btn" onClick={onUpdateStatus}>
        Update status
      </button>

      {f.type === "evacuation_center" &&
        (confirming ? (
          <div className="evac-confirm" role="group" aria-label="Confirm removal" ref={confirmRef}>
            <p className="evac-confirm-text">Remove this evacuation center from the map?</p>
            {removeError && (
              <p className="status-form-error" role="alert">
                {removeError}
              </p>
            )}
            <div className="evac-confirm-actions">
              <button
                type="button"
                className="evac-confirm-keep"
                disabled={removing}
                onClick={() => {
                  setConfirming(false);
                  setRemoveError(null);
                }}
              >
                Keep it
              </button>
              <button type="button" className="evac-confirm-yes" disabled={removing} onClick={remove}>
                {removing ? "Removing…" : removeError ? "Try again" : "Yes, remove"}
              </button>
            </div>
          </div>
        ) : (
          <button type="button" className="evac-remove-btn" onClick={() => setConfirming(true)}>
            Remove from map
          </button>
        ))}
    </section>
  );
}
