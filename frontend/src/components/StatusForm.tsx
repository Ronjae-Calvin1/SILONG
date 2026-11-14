import { useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { Facility, FacilityStatus, ResourceName, StatusPayload, StatusValue } from "../types";
import { Icon } from "./icons";
import {
  NOTE_MAX,
  RESOURCE_OPTIONS,
  STATUS_OPTIONS,
  STATUS_SYMBOL,
  facilityKindLabel,
  statusHint,
} from "./statusInfo";
import "./StatusPanel.css";
import "./FacilityPanel.css";

interface Props {
  facility: Facility;
  onClose: () => void;
  // The new status as the server saved it. `status.message` is set when the server changed
  // what was sent (auto-saved as full); the parent shows it.
  onSaved: (facilityId: number, status: FacilityStatus) => void;
  // Opened from "Set capacity": put the cursor in the capacity field and say what to do.
  focusCapacity?: boolean;
}

// Problems found in a number field before anything is sent.
interface FieldErrors {
  people?: string;
  capacity?: string;
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
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const peopleRef = useRef<HTMLInputElement>(null);
  const capacityRef = useRef<HTMLInputElement>(null);

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
      const problems: FieldErrors = {};
      if (p !== undefined && Number.isNaN(p)) problems.people = "People inside must be a whole number, like 85.";
      if (c !== undefined && Number.isNaN(c)) problems.capacity = "Maximum capacity must be a whole number, like 100.";
      else if (c === 0) problems.capacity = "Maximum capacity must be at least 1.";
      if (problems.people || problems.capacity) {
        setFieldErrors(problems);
        setError("Please fix the highlighted fields.");
        (problems.people ? peopleRef : capacityRef).current?.focus(); // also scrolls it into view
        return;
      }
      if (p !== undefined) payload.people_inside = p;
      if (c !== undefined) payload.max_capacity = c;
      if (resources.length > 0) payload.resources = resources;
    }

    setSaving(true);
    setError(null);
    setFieldErrors({});
    try {
      const saved = await api.submitStatus(f.id, payload);
      onSaved(f.id, saved); // parent closes the form, updates the pin and shows the confirmation
    } catch (err) {
      // Keep everything the user typed; just show what went wrong.
      if (err instanceof ApiError) setError(err.message);
      else setError("Something went wrong. Please try again.");
      setSaving(false);
    }
  }

  return (
    <div className="sf-backdrop" role="dialog" aria-modal="true" aria-label="Update status">
      <form className="sf-sheet" onSubmit={submit} noValidate>
        <header className="sf-header">
          <div className="sf-title-block">
            <h2 className="sf-title">Update status</h2>
            <p className="sf-sub">
              {f.name} · {facilityKindLabel(f)}
            </p>
          </div>
          <button type="button" className="fp-close" onClick={onClose} aria-label="Close form">
            <Icon name="close" />
          </button>
        </header>

        <div className="sf-body">
          {isEvac && focusCapacity && (
            <p className="sf-notice">
              Enter the maximum capacity below, then pick the status right now. A report needs both.
            </p>
          )}

          <fieldset className="sf-group">
            <legend className="sf-legend">{isEvac ? "How full is it right now?" : "What is its status right now?"}</legend>
            {STATUS_OPTIONS[f.type].map((o) => (
              <label className="sf-choice" key={o.value} data-status={o.value}>
                <input
                  type="radio"
                  name="facility-status"
                  className="sf-radio"
                  value={o.value}
                  checked={status === o.value}
                  onChange={() => setStatus(o.value)}
                />
                <span className="sf-choice-body">
                  <span className="sf-dot" aria-hidden="true">
                    {STATUS_SYMBOL[o.value]}
                  </span>
                  <span className="sf-choice-text">
                    <span className="sf-choice-title">{o.label}</span>
                    <span className="sf-choice-hint">{statusHint(f.type, o.value)}</span>
                  </span>
                  <span className="sf-choice-check" aria-hidden="true">
                    {"\u2713"}
                  </span>
                </span>
              </label>
            ))}
          </fieldset>

          {isEvac && (
            <>
              <div className="sf-row">
                <label className="sf-field">
                  <span className="sf-label">
                    Maximum capacity <span className="sf-optional">(optional)</span>
                  </span>
                  <input
                    ref={peopleRef}
                    className="sf-input"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    placeholder="e.g. 85"
                    value={people}
                    aria-invalid={!!fieldErrors.people}
                    aria-describedby={fieldErrors.people ? "sf-people-error" : undefined}
                    onChange={(e) => {
                      setPeople(e.target.value);
                      setFieldErrors((cur) => ({ ...cur, people: undefined }));
                    }}
                  />
                  {fieldErrors.people && (
                    <span className="sf-field-error" id="sf-people-error">
                      {fieldErrors.people}
                    </span>
                  )}
                </label>
                <label className="sf-field">
                  <span className="sf-label">
                    Maximum capacity <span className="sf-optional">(optional)</span>
                  </span>
                  <input
                    ref={capacityRef}
                    className="sf-input"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    placeholder="e.g. 100"
                    autoFocus={focusCapacity}
                    value={capacity}
                    aria-invalid={!!fieldErrors.capacity}
                    aria-describedby={fieldErrors.capacity ? "sf-capacity-error" : undefined}
                    onChange={(e) => {
                      setCapacity(e.target.value);
                      setFieldErrors((cur) => ({ ...cur, capacity: undefined }));
                    }}
                  />
                  {fieldErrors.capacity && (
                    <span className="sf-field-error" id="sf-capacity-error">
                      {fieldErrors.capacity}
                    </span>
                  )}
                </label>
              </div>

              <fieldset className="sf-group">
                <legend className="sf-legend">
                  What is available? <span className="sf-optional">(optional)</span>
                </legend>
                <div className="sf-chips">
                  {RESOURCE_OPTIONS.map((r) => (
                    <label key={r.value} className="sf-chip">
                      <input
                        type="checkbox"
                        className="sf-radio"
                        checked={resources.includes(r.value)}
                        onChange={() => toggleResource(r.value)}
                      />
                      <span className="sf-chip-body">
                        <span className="sf-chip-check" aria-hidden="true">
                          {"\u2713"}
                        </span>
                        {r.label}
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
            </>
          )}

          <label className="sf-field">
            <span className="sf-label">
              Short note <span className="sf-optional">(optional)</span>
            </span>
            <textarea
              className="sf-input sf-textarea"
              rows={2}
              maxLength={NOTE_MAX}
              placeholder="e.g. Gym is full, classrooms still open."
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <span className="sf-counter">
              {note.length}/{NOTE_MAX}
            </span>
          </label>

          <p className="sf-footnote">You can only update the status. Name, address and phone number can’t be changed here.</p>
        </div>

        <footer className="sf-footer">
          {error && (
            <p className="sf-error" role="alert">
              <span aria-hidden="true">{"\u26A0"}</span> {error}
            </p>
          )}
          <button type="submit" className="sf-submit" disabled={!status || saving}>
            {saving ? "Sending…" : error ? "Try again" : "Submit"}
          </button>
          {!status && <p className="sf-hint">Pick a status above to continue.</p>}
        </footer>
      </form>
    </div>
  );
}