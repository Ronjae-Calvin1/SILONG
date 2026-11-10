import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Icon } from "./icons";
import { LocationPicker, type Point } from "./LocationPicker";
import "./IncidentPanel.css";

type Props = {
  open: boolean;
  onClose: () => void;
};

type Form = {
  name: string;
  contact: string;
  kind: string;
  details: string;
  when: string;
  location: string;
};

// Messages shown under the required fields.
type Errors = { kind?: string; details?: string; location?: string };

type Preview = { id: string; name: string; url: string };

const DRAFT_KEY = "typhoon-prep:incident-draft"; // unfinished form
const REPORTS_KEY = "typhoon-prep:incident-reports"; // list of saved reports

const KINDS = ["Medical", "Missing person", "Flood", "Accident", "Violence", "Road blocked", "Other"];

const EMPTY: Form = { name: "", contact: "", kind: "", details: "", when: "", location: "" };

// Gives the current time in the format <input type="datetime-local"> expects.
function nowLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); // convert to local time
  return d.toISOString().slice(0, 16);
}

function loadDraft(): Form {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return EMPTY;
    const data = JSON.parse(raw) as Partial<Form>;
    return {
      name: typeof data.name === "string" ? data.name : "",
      contact: typeof data.contact === "string" ? data.contact : "",
      kind: typeof data.kind === "string" ? data.kind : "",
      details: typeof data.details === "string" ? data.details : "",
      when: typeof data.when === "string" ? data.when : "",
      location: typeof data.location === "string" ? data.location : "",
    };
  } catch {
    return EMPTY;
  }
}

function saveDraft(form: Form) {
  try {
    // A date on its own is not a draft, so ignore "when" when checking if the form is empty.
    const isEmpty = Object.entries(form).every(([key, v]) => key === "when" || v === "");
    if (isEmpty) localStorage.removeItem(DRAFT_KEY);
    else localStorage.setItem(DRAFT_KEY, JSON.stringify(form));
  } catch {
    // Storage may be blocked. The form still works, it just won't be remembered.
  }
}

function saveReport(form: Form, point: Point | null, imageNames: string[]): boolean {
  try {
    const raw = localStorage.getItem(REPORTS_KEY);
    const list: unknown = raw ? JSON.parse(raw) : [];
    const reports = Array.isArray(list) ? list : [];
    reports.push({
      ...form,
      latitude: point ? point.lat : null,
      longitude: point ? point.lng : null,
      imageNames,
      savedAt: new Date().toISOString(),
    });
    localStorage.setItem(REPORTS_KEY, JSON.stringify(reports));
    return true;
  } catch {
    return false;
  }
}

export function IncidentPanel({ open, onClose }: Props) {
  const [form, setForm] = useState<Form>(loadDraft);
  const [point, setPoint] = useState<Point | null>(null); // the pin on the mini map
  const [mapReady, setMapReady] = useState(false); // becomes true the first time the panel opens
  const [previews, setPreviews] = useState<Preview[]>([]);
  const [errors, setErrors] = useState<Errors>({});
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  // Size of the area not covered by the phone keyboard (null = use full screen).
  const [viewport, setViewport] = useState<{ h: number; top: number } | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const previewsRef = useRef<Preview[]>([]);
  previewsRef.current = previews;

  useEffect(() => {
    saveDraft(form);
  }, [form]);

  useEffect(() => {
    if (!open) {
      setStatus(null);
    } else {
      closeRef.current?.focus({ preventScroll: true });
      setMapReady(true); // the mini map is only created once someone opens the panel
      // "When did it happen?" starts as now. The person can still change it.
      setForm((f) => (f.when ? f : { ...f, when: nowLocal() }));
    }
  }, [open]);

  // Follow the visible screen so the phone keyboard never hides the Submit button.
  useEffect(() => {
    const vv = window.visualViewport;
    if (!open || !vv) return;
    function update() {
      if (vv) setViewport({ h: vv.height, top: vv.offsetTop });
    }
    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
      setViewport(null);
    };
  }, [open]);

  // Free the photo previews when the panel is removed.
  useEffect(() => {
    return () => {
      previewsRef.current.forEach((p) => URL.revokeObjectURL(p.url));
    };
  }, []);

  function change(field: keyof Form, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
    setErrors({}); // the person is fixing it, so remove old error messages
    setStatus(null);
  }

  function onPinChange(p: Point | null) {
    setPoint(p);
    setErrors({});
    setStatus(null);
  }

  function onPickImages(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []).filter((f) => f.type.startsWith("image/"));
    const added = files.map((f, i) => ({
      id: `${Date.now()}-${i}-${f.name}`,
      name: f.name,
      url: URL.createObjectURL(f), // temporary link used only to show the preview
    }));
    setPreviews((p) => [...p, ...added]);
    setStatus(null);
    e.target.value = ""; // lets the person pick the same photo again
  }

  function removeImage(id: string) {
    setPreviews((list) => {
      const gone = list.find((p) => p.id === id);
      if (gone) URL.revokeObjectURL(gone.url);
      return list.filter((p) => p.id !== id);
    });
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    const next: Errors = {};
    if (!form.kind) next.kind = "Please choose the type of incident.";
    if (!form.details.trim()) next.details = "Please describe what happened.";
    // The location can be a pin (map or GPS) OR a typed description.
    if (!point && !form.location.trim()) {
      next.location = "Please drop a pin on the map, use your GPS, or describe the place.";
    }
    if (next.kind || next.details || next.location) {
      setErrors(next);
      setStatus({ kind: "error", text: "Please fix the highlighted fields." });
      return;
    }
    setErrors({});

    const ok = saveReport(
      form,
      point,
      previews.map((p) => p.name)
    );
    if (!ok) {
      setStatus({
        kind: "error",
        text: "Could not save on this phone (storage may be blocked or full).",
      });
      return;
    }
    previews.forEach((p) => URL.revokeObjectURL(p.url));
    setPreviews([]);
    setPoint(null);
    setForm(EMPTY);
    // Only shown after the save really worked.
    setStatus({ kind: "ok", text: "Report saved on this phone" });
  }

  // Same 78% height as the other panels, but never taller than the space above the phone keyboard.
  const panelH = viewport ? Math.min(viewport.h, Math.round(window.innerHeight * 0.78)) : 0;
  const classes = ["ir-panel"];
  if (open) classes.push("ir-panel-open");

  return (
    <section
      className={classes.join(" ")}
      role="dialog"
      aria-modal="true"
      aria-labelledby="incident-title"
      inert={!open}
      // Keeps the panel at the BOTTOM of the visible area (above the keyboard).
      style={viewport ? { top: viewport.top + viewport.h - panelH, bottom: "auto", height: panelH } : undefined}
    >
      <div className="ir-top">
        <button type="button" className="ir-handle-btn" aria-label="Close incident report" onClick={onClose}>
          <span className="ir-handle" aria-hidden="true" />
        </button>
        <header className="ir-header">
          <h2 className="ir-title" id="incident-title">
            Submit Incident Report
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="ir-close"
            aria-label="Close incident report"
            onClick={onClose}
          >
            <Icon name="close" size={24} />
          </button>
        </header>
      </div>

      <form className="ir-form" onSubmit={onSubmit} noValidate>
        <div className="ir-body">
          <div className="ir-note ir-note-danger" role="note">
            <strong>If someone is in danger, call 911 first.</strong>
          </div>

          <div className="ir-field">
            <label className="ir-label" htmlFor="incident-kind">
              What is the incident? <span className="ir-hint">required</span>
            </label>
            <select
              id="incident-kind"
              className="ir-input ir-select"
              value={form.kind}
              aria-invalid={errors.kind ? true : undefined}
              aria-describedby={errors.kind ? "incident-kind-error" : undefined}
              onChange={(e) => change("kind", e.target.value)}
            >
              <option value="">Type of incident</option>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
            {errors.kind && (
              <p className="ir-error" id="incident-kind-error">
                {errors.kind}
              </p>
            )}
          </div>

          <div className="ir-field">
            <label className="ir-label" htmlFor="incident-details">
              What happened? <span className="ir-hint">required</span>
            </label>
            <textarea
              id="incident-details"
              className="ir-input ir-textarea"
              placeholder="Describe what you saw"
              value={form.details}
              aria-invalid={errors.details ? true : undefined}
              aria-describedby={errors.details ? "incident-details-error" : undefined}
              onChange={(e) => change("details", e.target.value)}
            />
            {errors.details && (
              <p className="ir-error" id="incident-details-error">
                {errors.details}
              </p>
            )}
          </div>

          <div className="ir-field">
            <label className="ir-label" htmlFor="incident-when">
              When did the incident happen? <span className="ir-hint">optional</span>
            </label>
            <input
              id="incident-when"
              className="ir-input"
              type="datetime-local"
              value={form.when}
              onChange={(e) => change("when", e.target.value)}
            />
            <button type="button" className="ir-link-btn" onClick={() => change("when", nowLocal())}>
              Use current time
            </button>
          </div>

          <div className="ir-field">
            {mapReady && <LocationPicker value={point} onChange={onPinChange} />}

            <label className="ir-label ir-label-sub" htmlFor="incident-location">
              Describe the place <span className="ir-hint">landmark, street or barangay</span>
            </label>
            <textarea
              id="incident-location"
              className="ir-input ir-textarea ir-textarea-short"
              placeholder="e.g. In front of the barangay hall"
              value={form.location}
              aria-invalid={errors.location ? true : undefined}
              aria-describedby={errors.location ? "incident-location-error" : undefined}
              onChange={(e) => change("location", e.target.value)}
            />
            {errors.location && (
              <p className="ir-error" id="incident-location-error">
                {errors.location}
              </p>
            )}
          </div>

          <div className="ir-field">
            <p className="ir-label">
              Photos <span className="ir-hint">optional</span>
            </p>
            <input
              id="incident-images"
              className="ir-file-input"
              type="file"
              accept="image/*"
              multiple
              onChange={onPickImages}
            />
            <label className="ir-upload" htmlFor="incident-images">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 16V4M7 9l5-5 5 5M4 20h16" />
              </svg>
              <span>Upload Photo</span>
              <small>Preview only. Nothing is uploaded.</small>
            </label>
            {previews.length > 0 && (
              <ul className="ir-previews">
                {previews.map((p) => (
                  <li className="ir-preview" key={p.id}>
                    <img src={p.url} alt={`Preview of ${p.name}`} />
                    <button
                      type="button"
                      className="ir-preview-remove"
                      aria-label={`Remove ${p.name}`}
                      onClick={() => removeImage(p.id)}
                    >
                      <Icon name="close" size={18} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="ir-field">
            <label className="ir-label" htmlFor="incident-name">
              Your name <span className="ir-hint">optional</span>
            </label>
            <input
              id="incident-name"
              className="ir-input"
              type="text"
              autoComplete="name"
              placeholder="Reporter's name"
              value={form.name}
              onChange={(e) => change("name", e.target.value)}
            />
          </div>

          <div className="ir-field">
            <label className="ir-label" htmlFor="incident-contact">
              Contact number <span className="ir-hint">optional</span>
            </label>
            <input
              id="incident-contact"
              className="ir-input"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              placeholder="e.g. 0917 123 4567"
              value={form.contact}
              onChange={(e) => change("contact", e.target.value)}
            />
          </div>

          <p className="ir-note">Your report is saved on this phone for now.</p>
        </div>

        {/* Stays at the bottom, outside the scrolling part */}
        <div className="ir-footer">
          {status && (
            <p
              className={`ir-status ${status.kind === "ok" ? "ir-status-ok" : "ir-status-error"}`}
              role={status.kind === "ok" ? "status" : "alert"}
            >
              {status.text}
            </p>
          )}
          <button type="submit" className="ir-submit">
            Submit report
          </button>
        </div>
      </form>
    </section>
  );
}