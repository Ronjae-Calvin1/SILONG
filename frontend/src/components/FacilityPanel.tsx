import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Facility } from "../types";
import { CapacityIndicator } from "./CapacityIndicator";
import { Icon } from "./icons";
import {
  RESOURCE_OPTIONS,
  STATUS_SYMBOL,
  clockTime,
  facilityKindLabel,
  phoneLinks,
  statusKey,
  statusLabel,
  timeAgo,
} from "./statusInfo";
import "./StatusPanel.css";
import "./EvacManager.css";
import "./FacilityPanel.css";

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
  onSetCapacity: () => void; // opens the update form with the capacity field ready (centers without a capacity)
  onRemoved: (facilityId: number) => void; // the server hid the center; the page removes its pin
}

// Details for the tapped pin: info, current status, capacity (evacuation centers) and the
// "Update status" button. Evacuation centers also get "Remove from map" (with a confirmation step).
export function FacilityPanel({ facility: f, onClose, onUpdateStatus, onSetCapacity, onRemoved }: Props) {
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
  const key = statusKey(f);
  const phones = phoneLinks(f.contact);

  return (
    <section className="fp-panel" aria-label={`${f.name} details`}>
      {/* Top part stays in place: handle (look only, the panel does not drag yet) + title + close. */}
      <div className="fp-top">
        <span className="fp-handle" aria-hidden="true" />

        <header className="fp-header">
          <div className="fp-title-block">
            <p className="fp-kind">{facilityKindLabel(f)}</p>
            <h2 className="fp-name">{f.name}</h2>
            {f.address && (
              <p className="fp-address">
                <Icon name="pin" size={16} />
                <span>{f.address}</span>
              </p>
            )}
          </div>
          <button type="button" className="fp-close" onClick={onClose} aria-label="Close details">
            <Icon name="close" />
          </button>
        </header>
      </div>

      {/* Middle part scrolls when there is a lot to show. */}
      <div className="fp-scroll">

      {/* Status card: status badge, capacity (centers) and when it was last reported. */}
      <div className="fp-card">
        <div className="fp-status-row">
          <span className="fp-badge" data-status={key} data-outdated={f.is_outdated ? "true" : "false"}>
            <span className="fp-badge-symbol" aria-hidden="true">
              {STATUS_SYMBOL[key]}
            </span>
            {statusLabel(f)}
          </span>
          {f.is_outdated && <span className="fp-outdated">May be outdated</span>}
        </div>

        {/* Works with or without a status: a new center has no status yet but does have a capacity. */}
        {f.type === "evacuation_center" && <CapacityIndicator facility={f} onSetCapacity={onSetCapacity} />}

        {s ? (
          <p className="fp-updated">
            Last updated {timeAgo(s.updated_at, now)} · {clockTime(s.updated_at, now)}
          </p>
        ) : (
          <p className="fp-updated">Nobody has reported yet. Be the first to update.</p>
        )}
      </div>

      {f.type === "evacuation_center" && s && (
        <div className="fp-section">
          <h3 className="fp-section-title">Still available</h3>
          <ul className="fp-chips">
            {RESOURCE_OPTIONS.map((r) => {
              const on = s.resources.includes(r.value);
              return (
                <li className="fp-chip" data-on={on} key={r.value}>
                  {on && <span aria-hidden="true">{"\u2713"} </span>}
                  {r.label}
                  {!on && <span className="fp-sr"> (not reported)</span>}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {s?.note && <p className="fp-note">“{s.note}”</p>}

      <div className="fp-section">
        <h3 className="fp-section-title">Contact</h3>
        {phones.length > 0 ? (
          <ul className="fp-contacts">
            {phones.map((p) => (
              <li key={p.href + p.text}>
                <a className="fp-contact-link" href={p.href}>
                  <Icon name="phone" size={18} />
                  {p.text}
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="fp-no-contact">No contact number listed yet.</p>
        )}
      </div>

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
          <button type="button" className="fp-remove-btn" onClick={() => setConfirming(true)}>
            Remove from map
          </button>
        ))}
      </div>

      <div className="fp-actions">
        <button type="button" className="fp-btn fp-btn-update" onClick={onUpdateStatus}>
          Update status
        </button>

        {phones.length > 0 ? (
          <a className="fp-btn fp-btn-call" href={phones[0].href} aria-label={`Call ${phones[0].text}`}>
            <Icon name="phone" size={20} />
            Call
          </a>
        ) : (
          <button type="button" className="fp-btn fp-btn-call" disabled aria-label="Call (no number listed)">
            <Icon name="phone" size={20} />
            Call
          </button>
        )}
      </div>
    </section>
  );
}