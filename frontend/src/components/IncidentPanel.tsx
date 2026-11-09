import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Icon } from "./icons";

type Props = {
  open: boolean;
  onClose: () => void;
};

type Form = {
  name: string;
  kind: string;
  details: string;
  when: string;
  location: string;
};

type Preview = { id: string; name: string; url: string };

const DRAFT_KEY = "typhoon-prep:incident-draft"; // unfinished form
const REPORTS_KEY = "typhoon-prep:incident-reports"; // list of saved reports

const KINDS = ["Medical", "Missing person", "Flood", "Accident", "Violence", "Other"];

const EMPTY: Form = { name: "", kind: "", details: "", when: "", location: "" };

function loadDraft(): Form {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return EMPTY;
    const data = JSON.parse(raw) as Partial<Form>;
    return {
      name: typeof data.name === "string" ? data.name : "",
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
    const isEmpty = Object.values(form).every((v) => v === "");
    if (isEmpty) localStorage.removeItem(DRAFT_KEY);
    else localStorage.setItem(DRAFT_KEY, JSON.stringify(form));
  } catch {
  }
}

function saveReport(form: Form, imageNames: string[]): boolean {
  try {
    const raw = localStorage.getItem(REPORTS_KEY);
    const list: unknown = raw ? JSON.parse(raw) : [];
    const reports = Array.isArray(list) ? list : [];
    reports.push({ ...form, imageNames, savedAt: new Date().toISOString() });
    localStorage.setItem(REPORTS_KEY, JSON.stringify(reports));
    return true;
  } catch {
    return false;
  }
}

export function IncidentPanel({ open, onClose }: Props) {
  const [form, setForm] = useState<Form>(loadDraft);
  const [previews, setPreviews] = useState<Preview[]>([]);
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
    }
  }, [open]);

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

  useEffect(() => {
    return () => {
      previewsRef.current.forEach((p) => URL.revokeObjectURL(p.url));
    };
  }, []);

  function change(field: keyof Form, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
    setStatus(null);
  }

  function onPickImages(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []).filter((f) => f.type.startsWith("image/"));
    const added = files.map((f, i) => ({
      id: `${Date.now()}-${i}-${f.name}`,
      name: f.name,
      url: URL.createObjectURL(f), 
    }));
    setPreviews((p) => [...p, ...added]);
    setStatus(null);
    e.target.value = ""; 
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
    if (!form.kind || !form.details.trim()) {
      setStatus({
        kind: "error",
        text: "Please choose what the incident is and add some details.",
      });
      return;
    }
    const ok = saveReport(
      form,
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
    setForm(EMPTY);
    setStatus({ kind: "ok", text: "Report saved on this phone" });
  }

    // Same 78% height as the other panels, but never taller than the space above the phone keyboard.
  const panelH = viewport ? Math.min(viewport.h, Math.round(window.innerHeight * 0.78)) : 0;
  const classes = ["incident-panel"];
  if (open) classes.push("incident-panel-open");

  return (
    <section
      className={classes.join(" ")}
      role="dialog"
      aria-modal="true"
      aria-labelledby="incident-title"
      aria-hidden={!open}
      style={viewport ? { top: viewport.top, bottom: "auto", height: panelH } : undefined}
    >
      <header className="incident-header">
        <h2 className="incident-title" id="incident-title">
          Submit Incident Report
        </h2>
        <button
          ref={closeRef}
          type="button"
          className="incident-close"
          aria-label="Close incident report"
          onClick={onClose}
        >
          <Icon name="close" size={22} />
        </button>
      </header>

      <form className="incident-form" onSubmit={onSubmit} noValidate>
        <div className="incident-body">
          <div className="incident-info" role="note">
            <span className="incident-info-icon" aria-hidden="true">
              i
            </span>
            <span>Your report is saved on this phone for now.</span>
          </div>

          <div className="incident-field">
            <label className="incident-label" htmlFor="incident-name">
              Your Name
            </label>
            <input
              id="incident-name"
              className="incident-input"
              type="text"
              autoComplete="name"
              value={form.name}
              onChange={(e) => change("name", e.target.value)}
            />
          </div>

          <div className="incident-field">
            <label className="incident-label" htmlFor="incident-kind">
              What's the incident?
            </label>
            <select
              id="incident-kind"
              className="incident-input"
              value={form.kind}
              onChange={(e) => change("kind", e.target.value)}
            >
              <option value="">Select…</option>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </div>

          <div className="incident-field">
            <label className="incident-label" htmlFor="incident-details">
              Provide details about what happened
            </label>
            <textarea
              id="incident-details"
              className="incident-input incident-textarea"
              value={form.details}
              onChange={(e) => change("details", e.target.value)}
            />
          </div>

          <div className="incident-field">
            <label className="incident-label" htmlFor="incident-when">
              When did this incident happen?
            </label>
            <input
              id="incident-when"
              className="incident-input"
              type="datetime-local"
              value={form.when}
              onChange={(e) => change("when", e.target.value)}
            />
          </div>

          <div className="incident-field">
            <p className="incident-label">Images</p>
            <input
              id="incident-images"
              className="incident-file-input"
              type="file"
              accept="image/*"
              multiple
              onChange={onPickImages}
            />
            <label className="incident-upload" htmlFor="incident-images">
              <span>Click to upload images</span>
              <small>Preview only. Nothing is uploaded.</small>
            </label>
            {previews.length > 0 && (
              <ul className="incident-previews">
                {previews.map((p) => (
                  <li className="incident-preview" key={p.id}>
                    <img src={p.url} alt={`Preview of ${p.name}`} />
                    <button
                      type="button"
                      className="incident-preview-remove"
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

          <div className="incident-field">
            <label className="incident-label" htmlFor="incident-location">
              Location of the incident
            </label>
            <textarea
              id="incident-location"
              className="incident-input incident-textarea"
              value={form.location}
              onChange={(e) => change("location", e.target.value)}
            />
          </div>
        </div>

        {/* Stays at the bottom, outside the scrolling part */}
        <div className="incident-footer">
          {status && (
            <p
              className={`incident-status ${
                status.kind === "ok" ? "incident-status-ok" : "incident-status-error"
              }`}
              role={status.kind === "ok" ? "status" : "alert"}
            >
              {status.text}
            </p>
          )}
          <button type="submit" className="incident-submit">
            Submit
          </button>
        </div>
      </form>
    </section>
  );
}