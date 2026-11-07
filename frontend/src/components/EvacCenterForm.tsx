import { useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { CenterType, Facility, NewEvacuationCenter } from "../types";
import type { CenterDraft } from "./evacCenterDraft";
import { Icon } from "./icons";
import { NOTE_MAX } from "./statusInfo";
import "./StatusPanel.css";
import "./EvacManager.css";

// Limits copied from the backend (backend/app/schemas.py) so mistakes are caught
// before anything is sent. The server still checks everything again.
const NAME_MIN = 2;
const NAME_MAX = 100;
const BARANGAY_MAX = 80;
const ADDRESS_MAX = 200;
const CONTACT_MAX = 60;
// Default of MAX_CAPACITY_LIMIT in backend/app/config.py (it can be changed there).
const CAPACITY_MAX = 50_000;

const TYPE_CHOICES: { value: CenterType; label: string }[] = [
  { value: "permanent", label: "Permanent" },
  { value: "temporary", label: "Temporary" },
];

interface FieldErrors {
  name?: string;
  centerType?: string;
  capacity?: string;
}

interface Props {
  point: { lng: number; lat: number };
  draft: CenterDraft;
  onDraftChange: (patch: Partial<CenterDraft>) => void;
  onBackToMap: () => void; // closes the form but keeps the pin and what was typed
  onSaved: (facility: Facility) => void;
}

// The backend trims and turns any run of spaces/newlines into one space before it
// checks lengths, so do the same here.
function tidy(text: string): string {
  return text.split(/\s+/).filter(Boolean).join(" ");
}

function round6(n: number): number {
  return Math.round(n * 1e6) / 1e6;
}

// Only the required fields are checked here. Optional ones are limited by maxLength on the inputs.
function validate(d: CenterDraft): FieldErrors {
  const errors: FieldErrors = {};

  const name = tidy(d.name);
  if (name.length === 0) errors.name = "Enter the name of the evacuation center.";
  else if (name.length < NAME_MIN || name.length > NAME_MAX) {
    errors.name = `Name must be ${NAME_MIN} to ${NAME_MAX} characters.`;
  }

  if (!d.centerType) errors.centerType = "Choose Permanent or Temporary.";

  const cap = d.capacity.trim();
  if (cap === "") errors.capacity = "Enter the maximum number of people the center can hold.";
  else if (!/^\d+$/.test(cap)) errors.capacity = "Use whole numbers only, like 200.";
  else if (Number(cap) < 1) errors.capacity = "Maximum capacity must be at least 1.";
  else if (Number(cap) > CAPACITY_MAX) {
    errors.capacity = `Maximum capacity can't be more than ${CAPACITY_MAX.toLocaleString("en-US")}.`;
  }

  return errors;
}

// Backend messages are already plain, except the "already exists" one, which ends
// with developer details: "(id 12)" and "(POST /api/evacuation-centers/12/restore)".
// Keep its sentences (including "It was removed earlier - restore it instead.") and drop those two bits.
function friendlyError(err: unknown): string {
  if (!(err instanceof ApiError)) return "Something went wrong. Please try again.";
  return err.message.replace(/\s*\(id \d+\)/, "").replace(/\s*\(POST [^)]*\)/, "");
}

export function EvacCenterForm({ point, draft, onDraftChange, onBackToMap, onSaved }: Props) {
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null); // from the server; typed values are kept
  const formRef = useRef<HTMLFormElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (saving) return;

    const found = validate(draft);
    setErrors(found);
    if (Object.keys(found).length > 0 || !draft.centerType) {
      // Bring the first problem into view (and focus it when it is a text field).
      // Only the form body is scrolled by hand: scrollIntoView() would also scroll
      // the map screen behind it, which has overflow hidden and would stay shifted.
      requestAnimationFrame(() => {
        const el = formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"], [data-invalid="true"]');
        const body = bodyRef.current;
        if (!el || !body) return;
        el.focus({ preventScroll: true });
        body.scrollTop += el.getBoundingClientRect().top - body.getBoundingClientRect().top - 24;
      });
      return;
    }

    // Empty optional fields are left out. The backend accepts no other fields.
    const payload: NewEvacuationCenter = {
      name: tidy(draft.name),
      center_type: draft.centerType,
      max_capacity: Number(draft.capacity.trim()),
      latitude: round6(point.lat),
      longitude: round6(point.lng),
    };
    if (tidy(draft.barangay)) payload.barangay = tidy(draft.barangay);
    if (tidy(draft.address)) payload.address = tidy(draft.address);
    if (tidy(draft.contact)) payload.contact = tidy(draft.contact);
    if (tidy(draft.note)) payload.note = tidy(draft.note);

    setSaving(true);
    setError(null);
    try {
      const created = await api.addEvacuationCenter(payload);
      onSaved(created); // parent puts the pin on the map and closes the form
    } catch (err) {
      // Keep everything the user typed; just show what went wrong.
      setError(friendlyError(err));
      setSaving(false);
    }
  }

  return (
    <div className="status-form-overlay" role="dialog" aria-modal="true" aria-label="Add evacuation center">
      <form className="status-form" onSubmit={submit} noValidate ref={formRef}>
        <header className="status-form-header">
          <div>
            <h2 className="status-form-title">Add evacuation center</h2>
            <p className="status-form-sub">
              Location: {point.lat.toFixed(5)}, {point.lng.toFixed(5)}
            </p>
          </div>
          <button type="button" className="panel-close" onClick={onBackToMap} aria-label="Back to map">
            <Icon name="close" />
          </button>
        </header>

        <div className="status-form-body" ref={bodyRef}>
          <button type="button" className="evac-link-btn" onClick={onBackToMap}>
            Change location on the map
          </button>

          <label className="status-field">
            Name
            <input
              className="status-input"
              value={draft.name}
              maxLength={NAME_MAX}
              autoComplete="off"
              aria-invalid={errors.name ? true : undefined}
              aria-describedby={errors.name ? "evac-name-error" : undefined}
              onChange={(e) => onDraftChange({ name: e.target.value })}
            />
            {errors.name && (
              <span className="evac-field-error" id="evac-name-error" role="alert">
                {errors.name}
              </span>
            )}
          </label>

          <fieldset className="status-choices evac-type" data-invalid={!!errors.centerType}>
            <legend>Type</legend>
            <div className="status-row">
              {TYPE_CHOICES.map((o) => (
                <button
                  type="button"
                  key={o.value}
                  className="status-choice"
                  aria-pressed={draft.centerType === o.value}
                  onClick={() => onDraftChange({ centerType: o.value })}
                >
                  {o.label}
                </button>
              ))}
            </div>
            {errors.centerType && (
              <span className="evac-field-error" role="alert">
                {errors.centerType}
              </span>
            )}
          </fieldset>

          <label className="status-field">
            Barangay (optional)
            <input
              className="status-input"
              value={draft.barangay}
              maxLength={BARANGAY_MAX}
              autoComplete="off"
              onChange={(e) => onDraftChange({ barangay: e.target.value })}
            />
          </label>

          <label className="status-field">
            Address (optional)
            <input
              className="status-input"
              value={draft.address}
              maxLength={ADDRESS_MAX}
              autoComplete="off"
              onChange={(e) => onDraftChange({ address: e.target.value })}
            />
          </label>

          <label className="status-field">
            Contact number (optional)
            <input
              className="status-input"
              type="tel"
              inputMode="tel"
              value={draft.contact}
              maxLength={CONTACT_MAX}
              autoComplete="off"
              onChange={(e) => onDraftChange({ contact: e.target.value })}
            />
          </label>

          <label className="status-field">
            Maximum capacity (number of people)
            <input
              className="status-input"
              inputMode="numeric"
              pattern="[0-9]*"
              value={draft.capacity}
              autoComplete="off"
              aria-invalid={errors.capacity ? true : undefined}
              aria-describedby={errors.capacity ? "evac-capacity-error" : undefined}
              onChange={(e) => onDraftChange({ capacity: e.target.value })}
            />
            {errors.capacity && (
              <span className="evac-field-error" id="evac-capacity-error" role="alert">
                {errors.capacity}
              </span>
            )}
          </label>

          <label className="status-field">
            Short note (optional)
            <textarea
              className="status-input"
              rows={2}
              maxLength={NOTE_MAX}
              value={draft.note}
              onChange={(e) => onDraftChange({ note: e.target.value })}
            />
            <small>
              {draft.note.length}/{NOTE_MAX}
            </small>
          </label>
        </div>

        <footer className="status-form-footer">
          {error && (
            <p className="status-form-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="status-submit" disabled={saving}>
            {saving ? "Saving…" : error ? "Try again" : "Save evacuation center"}
          </button>
        </footer>
      </form>
    </div>
  );
}
