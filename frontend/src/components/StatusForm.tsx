import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { Facility, FacilityStatus, ResourceName, StatusPayload, StatusValue } from "../types";
import { Icon } from "./icons";
import { NOTE_MAX, RESOURCE_OPTIONS, STATUS_OPTIONS, TYPE_LABEL } from "./statusInfo";
import "./StatusPanel.css";

interface Props {
  facility: Facility;
  onClose: () => void;
  // The new status as the server saved it. `status.message` is set when the server changed
  // what was sent (auto-saved as full); the parent shows it.
  onSaved: (facilityId: number, status: FacilityStatus) => void;
  // Opened from "Set capacity": put the cursor in the capacity field and say what to do.
  focusCapacity?: boolean;
}

// "" -> undefined, otherwise a whole number >= 0 (NaN if it is not one).
function toCount(text: string): number | undefined {
  const t = text.trim();
  if (t === "") return undefined;
  return /^\d+$/.test(t) ? Number(t) : NaN;
}

// Users can only send capacity/availability data, never name, address or phone.
export function StatusForm({ facility: f, onClose, onSaved, focusCapacity = false }: Props) {
  const isEvac = f.type === "evacuation_center";
  const [status, setStatus] = useState<StatusValue | null>(null);
  const [people, setPeople] = useState("");
  // Capacity rarely changes, so start from the center's current one (still editable). It comes
  // from the facility, not from the last report: a new center has a capacity but no report yet.
  const [capacity, setCapacity] = useState(f.max_capacity !== null ? String(f.max_capacity) : "");
  const [resources, setResources] = useState<ResourceName[]>([]);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleResource(r: ResourceName) {
    setResources((cur) => (cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r]));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!status || saving) return;

    const payload: StatusPayload = { status };
    const trimmedNote = note.trim();
    if (trimmedNote) payload.note = trimmedNote;

    if (isEvac) {
      const p = toCount(people);
      const c = toCount(capacity);
      if (Number.isNaN(p) || Number.isNaN(c)) {
        setError("People inside and maximum capacity must be whole numbers, like 85.");
        return;
      }
      if (c === 0) {
        setError("Maximum capacity must be at least 1.");
        return;
      }
      if (p !== undefined) payload.people_inside = p;
      if (c !== undefined) payload.max_capacity = c;
      if (resources.length > 0) payload.resources = resources;
    }

    setSaving(true);
    setError(null);
    try {
      const saved = await api.submitStatus(f.id, payload);
      onSaved(f.id, saved); // parent closes the form and updates the pin
    } catch (err) {
      // Keep everything the user typed; just show what went wrong.
      if (err instanceof ApiError) setError(err.message);
      else setError("Something went wrong. Please try again.");
      setSaving(false);
    }
  }

  return (
    <div className="status-form-overlay" role="dialog" aria-modal="true" aria-label="Update status">
      <form className="status-form" onSubmit={submit}>
        <header className="status-form-header">
          <div>
            <h2 className="status-form-title">Update status</h2>
            <p className="status-form-sub">
              {f.name} · {TYPE_LABEL[f.type]}
            </p>
          </div>
          <button type="button" className="panel-close" onClick={onClose} aria-label="Close form">
            <Icon name="close" />
          </button>
        </header>

        <div className="status-form-body">
          {isEvac && focusCapacity && (
            <p className="status-form-hint status-form-hint-left">
              Enter the maximum capacity below, then pick the status right now. A report needs both.
            </p>
          )}

          <fieldset className="status-choices">
            <legend>What is the status now?</legend>
            {STATUS_OPTIONS[f.type].map((o) => (
              <button
                type="button"
                key={o.value}
                className="status-choice"
                data-status={o.value}
                aria-pressed={status === o.value}
                onClick={() => setStatus(o.value)}
              >
                {o.label}
              </button>
            ))}
          </fieldset>

          {isEvac && (
            <>
              <div className="status-row">
                <label className="status-field">
                  People inside (optional)
                  <input
                    className="status-input"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={people}
                    onChange={(e) => setPeople(e.target.value)}
                  />
                </label>
                <label className="status-field">
                  Max capacity (optional)
                  <input
                    className="status-input"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    autoFocus={focusCapacity}
                    value={capacity}
                    onChange={(e) => setCapacity(e.target.value)}
                  />
                </label>
              </div>

              <fieldset className="status-resources">
                <legend>Available now (optional)</legend>
                {RESOURCE_OPTIONS.map((r) => (
                  <label key={r.value} className="status-check">
                    <input
                      type="checkbox"
                      checked={resources.includes(r.value)}
                      onChange={() => toggleResource(r.value)}
                    />
                    {r.label}
                  </label>
                ))}
              </fieldset>
            </>
          )}

          <label className="status-field">
            Short note (optional)
            <textarea
              className="status-input"
              rows={2}
              maxLength={NOTE_MAX}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <small>
              {note.length}/{NOTE_MAX}
            </small>
          </label>
        </div>

        <footer className="status-form-footer">
          {error && (
            <p className="status-form-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="status-submit" disabled={!status || saving}>
            {saving ? "Sending…" : error ? "Try again" : "Submit"}
          </button>
          {!status && <p className="status-form-hint">Pick a status above to continue.</p>}
        </footer>
      </form>
    </div>
  );
}
