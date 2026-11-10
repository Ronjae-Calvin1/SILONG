import { useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { CenterType, Facility, NewEvacuationCenter } from "../types";
import type { CenterDraft } from "./evacCenterDraft";
import { Icon } from "./icons";
import { NOTE_MAX } from "./statusInfo";
import "./EvacManager.css";
import "./EvacCenterForm.css";

// Limits copied from the backend (backend/app/schemas.py) so mistakes are caught
// before anything is sent. The server still checks everything again.
const NAME_MIN = 2;
const NAME_MAX = 100;
const BARANGAY_MAX = 80;
const ADDRESS_MAX = 200;
const CONTACT_MAX = 60;
// Default of MAX_CAPACITY_LIMIT in backend/app/config.py (it can be changed there).
const CAPACITY_MAX = 50_000;

const TYPE_CHOICES: { value: CenterType; label: string; hint: string }[] = [
  { value: "permanent", label: "Permanent", hint: "A building already used as a standing evacuation site." },
  { value: "temporary", label: "Temporary", hint: "A place opened only for a specific emergency." },
];

interface FieldErrors {
  name?: string;
  centerType?: string;
  capacity?: string;
  contact?: string;
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

  const contact = tidy(d.contact);
  if (contact) {
    const digits = contact.replace(/\D/g, "");
    if (!/^[0-9+()\-\s/,]+$/.test(contact)) {
      errors.contact = "Use numbers only (you can also use + - ( ) and spaces).";
    } else if (digits.length < 7) {
      errors.contact = "That phone number looks too short.";
    }
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

    // Typing in a field clears that field's error message.
  function change(patch: Partial<CenterDraft>) {
    onDraftChange(patch);
    setErrors((cur) => {
      const next = { ...cur };
      (Object.keys(patch) as (keyof FieldErrors)[]).forEach((k) => delete next[k]);
      return next;
    });
  }

  // When the user leaves a field, check just that field.
  function checkField(field: keyof FieldErrors) {
    setErrors((cur) => ({ ...cur, [field]: validate(draft)[field] }));
  }

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
    <div className="evac-form-overlay" role="dialog" aria-modal="true" aria-labelledby="evac-form-title">
      <form className="evac-form" onSubmit={submit} noValidate ref={formRef} aria-busy={saving}>
        <header className="evac-form-header">
          <div>
            <p className="evac-form-step">Step 2 of 2</p>
            <h2 className="evac-form-title" id="evac-form-title">
              Add evacuation center
            </h2>
          </div>
          <button
            type="button"
            className="evac-form-close"
            onClick={onBackToMap}
            aria-label="Back to map (your answers are kept)"
          >
            <Icon name="close" />
          </button>
        </header>

        <div className="evac-form-body" ref={bodyRef}>
          <p className="evac-form-note">
            Fields marked Required must be filled in. If you go back to the map, what you typed is kept.
          </p>

          {/* ---------- Basic information ---------- */}
          <section className="evac-section" aria-labelledby="evac-sec-basic">
            <h3 className="evac-section-title" id="evac-sec-basic">
              Basic information
            </h3>

            <div className="evac-field">
              <label className="evac-label" htmlFor="evac-name">
                Name <span className="evac-tag evac-tag-required">Required</span>
              </label>
              <input
                id="evac-name"
                className="evac-input"
                value={draft.name}
                maxLength={NAME_MAX}
                placeholder="e.g. Barangay Covered Court"
                autoComplete="off"
                aria-invalid={errors.name ? true : undefined}
                aria-describedby={errors.name ? "evac-name-error" : undefined}
                onChange={(e) => change({ name: e.target.value })}
                onBlur={() => checkField("name")}
              />
              {errors.name && (
                <p className="evac-error" id="evac-name-error" role="alert">
                  {errors.name}
                </p>
              )}
            </div>

            <fieldset
              className="evac-fieldset"
              data-invalid={!!errors.centerType}
              tabIndex={-1}
              aria-describedby={errors.centerType ? "evac-type-error" : undefined}
            >
              <legend className="evac-legend">
                Type <span className="evac-tag evac-tag-required">Required</span>
              </legend>
              <div className="evac-type-grid">
                {TYPE_CHOICES.map((o) => (
                  <label key={o.value} className="evac-type-card" data-checked={draft.centerType === o.value}>
                    <input
                      type="radio"
                      name="evac-center-type"
                      className="evac-type-input"
                      value={o.value}
                      checked={draft.centerType === o.value}
                      onChange={() => change({ centerType: o.value })}
                    />
                    <span className="evac-type-name">{o.label}</span>
                    <span className="evac-type-desc">{o.hint}</span>
                  </label>
                ))}
              </div>
              {errors.centerType && (
                <p className="evac-error" id="evac-type-error" role="alert">
                  {errors.centerType}
                </p>
              )}
            </fieldset>
          </section>

          {/* ---------- Location ---------- */}
          <section className="evac-section" aria-labelledby="evac-sec-location">
            <h3 className="evac-section-title" id="evac-sec-location">
              Location
            </h3>

            <div className="evac-location-card">
              <div>
                <p className="evac-location-label">Pin location</p>
                <p className="evac-location-value">
                  {point.lat.toFixed(5)}, {point.lng.toFixed(5)}
                </p>
              </div>
              <button type="button" className="evac-secondary-btn" onClick={onBackToMap}>
                Change on map
              </button>
            </div>

            <div className="evac-field">
              <label className="evac-label" htmlFor="evac-barangay">
                Barangay <span className="evac-tag evac-tag-optional">Optional</span>
              </label>
              <input
                id="evac-barangay"
                className="evac-input"
                value={draft.barangay}
                maxLength={BARANGAY_MAX}
                placeholder="e.g. Barangay 12"
                autoComplete="off"
                onChange={(e) => change({ barangay: e.target.value })}
              />
            </div>

            <div className="evac-field">
              <label className="evac-label" htmlFor="evac-address">
                Address <span className="evac-tag evac-tag-optional">Optional</span>
              </label>
              <input
                id="evac-address"
                className="evac-input"
                value={draft.address}
                maxLength={ADDRESS_MAX}
                placeholder="Street, subdivision, or landmark"
                autoComplete="off"
                onChange={(e) => change({ address: e.target.value })}
              />
            </div>
          </section>

          {/* ---------- Additional information ---------- */}
          <section className="evac-section" aria-labelledby="evac-sec-more">
            <h3 className="evac-section-title" id="evac-sec-more">
              Additional information
            </h3>

            <div className="evac-field">
              <label className="evac-label" htmlFor="evac-capacity">
                Maximum capacity <span className="evac-tag evac-tag-required">Required</span>
              </label>
              <input
                id="evac-capacity"
                className="evac-input"
                inputMode="numeric"
                pattern="[0-9]*"
                value={draft.capacity}
                placeholder="e.g. 200"
                autoComplete="off"
                aria-invalid={errors.capacity ? true : undefined}
                aria-describedby={errors.capacity ? "evac-capacity-error" : "evac-capacity-help"}
                // Only digits are accepted, so negative numbers, letters and decimals can't be typed.
                onChange={(e) => change({ capacity: e.target.value.replace(/\D/g, "") })}
                onBlur={() => checkField("capacity")}
              />
              {errors.capacity ? (
                <p className="evac-error" id="evac-capacity-error" role="alert">
                  {errors.capacity}
                </p>
              ) : (
                <p className="evac-help" id="evac-capacity-help">
                  The most people this center can hold. Whole numbers only.
                </p>
              )}
            </div>

            <div className="evac-field">
              <label className="evac-label" htmlFor="evac-contact">
                Contact number <span className="evac-tag evac-tag-optional">Optional</span>
              </label>
              <input
                id="evac-contact"
                className="evac-input"
                type="tel"
                inputMode="tel"
                value={draft.contact}
                maxLength={CONTACT_MAX}
                placeholder="e.g. 0917 123 4567"
                autoComplete="off"
                aria-invalid={errors.contact ? true : undefined}
                aria-describedby={errors.contact ? "evac-contact-error" : undefined}
                // Letters are removed as you type; only phone-number characters stay.
                onChange={(e) => change({ contact: e.target.value.replace(/[^0-9+()\-\s/,]/g, "") })}
                onBlur={() => checkField("contact")}
              />
              {errors.contact && (
                <p className="evac-error" id="evac-contact-error" role="alert">
                  {errors.contact}
                </p>
              )}
            </div>

            <div className="evac-field">
              <label className="evac-label" htmlFor="evac-note">
                Short note <span className="evac-tag evac-tag-optional">Optional</span>
              </label>
              <textarea
                id="evac-note"
                className="evac-input evac-textarea"
                rows={3}
                maxLength={NOTE_MAX}
                placeholder="Anything helpful, like which entrance to use"
                value={draft.note}
                onChange={(e) => change({ note: e.target.value })}
              />
              <p className="evac-counter">
                {draft.note.length}/{NOTE_MAX}
              </p>
            </div>
          </section>
        </div>

        <footer className="evac-form-footer">
          {error && (
            <p className="evac-form-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="evac-save-btn" disabled={saving}>
            {saving && <span className="evac-spinner" aria-hidden="true" />}
            {saving ? "Saving…" : error ? "Try again" : "Save evacuation center"}
          </button>
        </footer>
      </form>
    </div>
  );
}