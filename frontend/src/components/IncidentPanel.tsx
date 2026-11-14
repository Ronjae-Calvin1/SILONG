import { useEffect, useRef, useState, type FormEvent } from "react";
import { Icon } from "./icons";
import { LocationPicker, type Point } from "./LocationPicker";
import { REPORTS_KEY } from "./myActivity"; // the same list the menu's "My reports" reads
import "./IncidentPanel.css";
import "./ReportContent.css";

type Props = {
  open: boolean;
  onClose: () => void;
};

// "help" = the person needs help (responders only). "hazard" = a danger on the road, shown nearby after it is checked.
type Mode = "help" | "hazard";

type Form = {
  mode: Mode;
  kind: string;
  details: string;
  contact: string; // only asked in "I need help" mode, so responders can call back (required there)
  people: number; // only "I need help": how many people need help
  canMove: "" | "yes" | "no"; // only "I need help": can the person move?
};

// Messages shown under the fields.
type Errors = { kind?: string; contact?: string; canMove?: string; location?: string };

type WhereMode = "gps" | "map" | null;
type GpsState = { kind: "idle" | "busy" | "ok" | "error"; text: string };

const DRAFT_KEY = "typhoon-prep:incident-draft"; // unfinished form

const KINDS: Record<Mode, string[]> = {
  help: ["Medical", "Trapped", "Injured", "Need rescue", "Other"],
  hazard: ["Flooded road", "Fallen tree or pole", "Blocked road", "Landslide", "Other"],
};

const MAX_DETAILS = 200;
const MAX_KIND = 60; // longest "something else" a person can type

const MAX_PEOPLE = 99;

// A phone number needs at least 7 digits and may only use digits, spaces, + - ( ).
function isPhoneOk(value: string): boolean {
  const v = value.trim();
  return /^[\d\s+\-()]+$/.test(v) && v.replace(/\D/g, "").length >= 7;
}

const EMPTY: Form = { mode: "hazard", kind: "", details: "", contact: "", people: 1, canMove: "" };

function loadDraft(): Form {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return EMPTY;
    const data = JSON.parse(raw) as Partial<Form>;
    const mode: Mode = data.mode === "help" ? "help" : "hazard";
    // A saved kind is either one of the chips or something the person typed themselves.
    const kind = typeof data.kind === "string" ? data.kind.slice(0, MAX_KIND) : "";
    return {
      mode,
      kind,
      details: typeof data.details === "string" ? data.details.slice(0, MAX_DETAILS) : "",
      contact: typeof data.contact === "string" ? data.contact : "",
      people:
        typeof data.people === "number" && data.people >= 1 && data.people <= MAX_PEOPLE ? Math.round(data.people) : 1,
      canMove: data.canMove === "yes" || data.canMove === "no" ? data.canMove : "",
    };
  } catch {
    return EMPTY;
  }
}

function saveDraft(form: Form) {
  try {
    // Choosing a mode on its own is not a draft, so ignore "mode" when checking if the form is empty.
    const isEmpty =
      form.kind === "" && form.details === "" && form.contact === "" && form.canMove === "" && form.people === 1;
    if (isEmpty) localStorage.removeItem(DRAFT_KEY);
    else localStorage.setItem(DRAFT_KEY, JSON.stringify(form));
  } catch {
    // Storage may be blocked. The form still works, it just won't be remembered.
  }
}

function saveReport(form: Form, point: Point): boolean {
  try {
    const raw = localStorage.getItem(REPORTS_KEY);
    const list: unknown = raw ? JSON.parse(raw) : [];
    const reports = Array.isArray(list) ? list : [];
    const help = form.mode === "help";
    reports.push({
      mode: form.mode,
      kind: form.kind.trim(),
      details: form.details,
      // Only "I need help" reports keep a phone number, a head count and "can they move".
      contact: help ? form.contact.trim() : "",
      ...(help ? { people: form.people, canMove: form.canMove } : {}),
      latitude: point.lat,
      longitude: point.lng,
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
  const [point, setPoint] = useState<Point | null>(null); // where it happened (GPS or a pin on the mini map)
  const [whereMode, setWhereMode] = useState<WhereMode>(null);
  const [gps, setGps] = useState<GpsState>({ kind: "idle", text: "" });
  const [errors, setErrors] = useState<Errors>({});
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  // Size of the area not covered by the phone keyboard (null = use full screen).
  const [viewport, setViewport] = useState<{ h: number; top: number } | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

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

  // Follow the visible screen so the phone keyboard never hides the Send button.
  useEffect(() => {
    const vv = window.visualViewport;
    // On desktop the panel is a right-hand drawer sized by CSS, so skip this.
    if (!open || !vv || window.matchMedia("(min-width: 1024px)").matches) return;
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

  function chooseMode(mode: Mode) {
    if (mode === form.mode) return;
    // The list of choices is different for each mode, so the old choice is cleared.
    setForm((f) => ({ ...f, mode, kind: "" }));
    setErrors({});
    setStatus(null);
  }

  function chooseKind(kind: string) {
    setForm((f) => ({ ...f, kind }));
    setErrors((e) => ({ ...e, kind: undefined }));
    setStatus(null);
  }

  // The text box under the chips: what the person types becomes the "kind" and un-selects any chip.
  function typeKind(value: string) {
    setForm((f) => ({ ...f, kind: value.slice(0, MAX_KIND) }));
    setErrors((e) => ({ ...e, kind: undefined }));
    setStatus(null);
  }

  function change(field: "details" | "contact", value: string) {
    setForm((f) => ({ ...f, [field]: value }));
    if (field === "contact") setErrors((e) => ({ ...e, contact: undefined }));
    setStatus(null);
  }

  function setPeople(n: number) {
    setForm((f) => ({ ...f, people: Math.min(MAX_PEOPLE, Math.max(1, Math.round(n) || 1)) }));
    setStatus(null);
  }

  function chooseCanMove(v: "yes" | "no") {
    setForm((f) => ({ ...f, canMove: v }));
    setErrors((e) => ({ ...e, canMove: undefined }));
    setStatus(null);
  }

  function onPinChange(p: Point | null) {
    setPoint(p);
    setErrors((e) => ({ ...e, location: undefined }));
    setStatus(null);
  }

  function findMyLocation() {
    setWhereMode("gps");
    setStatus(null);
    if (!("geolocation" in navigator)) {
      setGps({ kind: "error", text: "This browser can't share your location. Use \"Pick on map\" instead." });
      return;
    }
    setGps({ kind: "busy", text: "Finding your location…" });
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setPoint({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setGps({ kind: "ok", text: `Location found · accurate to about ${Math.round(pos.coords.accuracy)} m` });
        setErrors((e) => ({ ...e, location: undefined }));
      },
      (err) => {
        let text = "Could not get your location. Use \"Pick on map\" instead.";
        if (err.code === err.PERMISSION_DENIED) {
          text = "Location is turned off for this site. Allow it in your browser settings, or use \"Pick on map\".";
        } else if (err.code === err.TIMEOUT) {
          text = "Finding your location took too long. Try again, or use \"Pick on map\".";
        }
        setGps({ kind: "error", text });
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  }

  function pickOnMap() {
    setWhereMode("map");
    setGps({ kind: "idle", text: "" });
    setStatus(null);
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    const next: Errors = {};
    const help = form.mode === "help";
    if (!form.kind.trim()) next.kind = help ? "Please choose what happened." : "Please choose what it is.";
    if (help && !form.canMove) next.canMove = "Please choose Yes or No.";
    if (help && !form.contact.trim()) next.contact = "Please enter a phone number so responders can reach you.";
    else if (help && !isPhoneOk(form.contact)) next.contact = "Please enter a valid phone number.";
    if (!point) next.location = "Please use your GPS location or pick the spot on the map.";
    if (next.kind || next.canMove || next.contact || next.location || !point) {
      setErrors(next);
      setStatus({ kind: "error", text: "Please fix the highlighted fields." });
      return;
    }
    setErrors({});

    if (!saveReport(form, point)) {
      setStatus({
        kind: "error",
        text: "Could not save on this phone (storage may be blocked or full).",
      });
      return;
    }
    setPoint(null);
    setWhereMode(null);
    setGps({ kind: "idle", text: "" });
    setForm((f) => ({ ...EMPTY, mode: f.mode }));
    // Only shown after the save really worked.
    setStatus({ kind: "ok", text: help ? "Request saved on this phone" : "Report saved on this phone" });
  }

  // Same 78% height as the other panels, but never taller than the space above the phone keyboard.
  const panelH = viewport ? Math.min(viewport.h, Math.round(window.innerHeight * 0.78)) : 0;
  const classes = ["ir-panel"];
  if (open) classes.push("ir-panel-open");

  const isHelp = form.mode === "help";

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
          {/* 911 shortcut */}
          <div className="ir-danger" role="note">
            <strong>In danger? Call 911 first.</strong>
            <a className="ir-danger-call" href="tel:911" aria-label="Call 911, the national emergency number">
              <Icon name="phone" size={18} />
              <span>Call 911</span>
            </a>
          </div>

          {/* Two choices: I need help / Report a hazard */}
          <div className="ir-modes" role="radiogroup" aria-label="Type of report">
            <button
              type="button"
              role="radio"
              aria-checked={isHelp}
              className="ir-mode ir-mode-help"
              onClick={() => chooseMode("help")}
            >
              <span className="ir-mode-icon" aria-hidden="true">
                <Icon name="warning" size={22} />
              </span>
              <span className="ir-mode-text">
                <strong>I need help</strong>
                <small>Goes to responders only. It is never shown on the map.</small>
              </span>
              {isHelp && <CheckMark />}
            </button>

            <button
              type="button"
              role="radio"
              aria-checked={!isHelp}
              className="ir-mode ir-mode-hazard"
              onClick={() => chooseMode("hazard")}
            >
              <span className="ir-mode-icon" aria-hidden="true">
                <Icon name="megaphone" size={22} />
              </span>
              <span className="ir-mode-text">
                <strong>Report a hazard</strong>
                <small>Nearby people may see it after it is checked.</small>
              </span>
              {!isHelp && <CheckMark />}
            </button>
          </div>

          {/* What happened? / What is it? */}
          <div className="ir-field">
            <p className="ir-label" id="incident-kind-label">
              {isHelp ? "What happened?" : "What is it?"}
            </p>
            <div className="ir-chips" role="group" aria-labelledby="incident-kind-label">
              {KINDS[form.mode].map((k) => (
                <button
                  key={k}
                  type="button"
                  className="ir-chip"
                  aria-pressed={form.kind === k}
                  onClick={() => chooseKind(k)}
                >
                  {k}
                </button>
              ))}
            </div>
            {/* Not in the list? They can type it here. Typing un-selects the chips, picking a chip clears this box. */}
            <input
              className="ir-input ir-input-light ir-kind-input"
              type="text"
              maxLength={MAX_KIND}
              aria-label={isHelp ? "Something else that happened" : "Something else you want to report"}
              aria-invalid={errors.kind ? true : undefined}
              placeholder={isHelp ? "Not in the list? Type what happened" : "Not in the list? Type what you want to report"}
              value={KINDS[form.mode].includes(form.kind) ? "" : form.kind}
              onChange={(e) => typeKind(e.target.value)}
            />
            {errors.kind && <p className="ir-error">{errors.kind}</p>}
          </div>

          {/* Only for "I need help": how many people, can they move, phone number */}
          {isHelp && (
            <>
              <div className="ir-field">
                <p className="ir-label" id="incident-people-label">
                  How many people need help?
                </p>
                <div className="ir-stepper" role="group" aria-labelledby="incident-people-label">
                  <button
                    type="button"
                    className="ir-stepper-btn"
                    aria-label="One less person"
                    disabled={form.people <= 1}
                    onClick={() => setPeople(form.people - 1)}
                  >
                    <span aria-hidden="true">−</span>
                  </button>
                  <input
                    className="ir-input ir-input-light ir-stepper-input"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={MAX_PEOPLE}
                    aria-label="Number of people"
                    value={form.people}
                    onChange={(e) => setPeople(Number(e.target.value))}
                  />
                  <button
                    type="button"
                    className="ir-stepper-btn"
                    aria-label="One more person"
                    disabled={form.people >= MAX_PEOPLE}
                    onClick={() => setPeople(form.people + 1)}
                  >
                    <span aria-hidden="true">+</span>
                  </button>
                </div>
              </div>

              <div className="ir-field">
                <p className="ir-label" id="incident-move-label">
                  Can the person move?
                </p>
                <div className="ir-yesno" role="group" aria-labelledby="incident-move-label">
                  <button
                    type="button"
                    className="ir-chip"
                    aria-pressed={form.canMove === "yes"}
                    onClick={() => chooseCanMove("yes")}
                  >
                    Yes
                  </button>
                  <button
                    type="button"
                    className="ir-chip"
                    aria-pressed={form.canMove === "no"}
                    onClick={() => chooseCanMove("no")}
                  >
                    No
                  </button>
                </div>
                {errors.canMove && <p className="ir-error">{errors.canMove}</p>}
              </div>

              <div className="ir-field">
                <label className="ir-label" htmlFor="incident-contact">
                  Phone number <span className="ir-hint">(required, only responders see it)</span>
                </label>
                <input
                  id="incident-contact"
                  className="ir-input ir-input-light"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel"
                  placeholder="e.g. 0917 123 4567"
                  aria-required="true"
                  aria-invalid={errors.contact ? true : undefined}
                  value={form.contact}
                  onChange={(e) => change("contact", e.target.value)}
                />
                {errors.contact && <p className="ir-error">{errors.contact}</p>}
              </div>
            </>
          )}

          {/* Where? */}
          <div className="ir-field ir-where">
            <p className="ir-label" id="incident-where-label">
              Where?
            </p>
            <div className="ir-where-buttons" role="group" aria-labelledby="incident-where-label">
              <button
                type="button"
                className="ir-where-btn"
                aria-pressed={whereMode === "gps"}
                onClick={findMyLocation}
                disabled={gps.kind === "busy"}
              >
                {whereMode === "gps" && gps.kind === "ok" && <CheckMark small />}
                <span>{gps.kind === "busy" ? "Locating…" : "My GPS location"}</span>
              </button>
              <button type="button" className="ir-where-btn" aria-pressed={whereMode === "map"} onClick={pickOnMap}>
                <Icon name="pin" size={18} />
                <span>Pick on map</span>
              </button>
            </div>

            {/* "I need help" + GPS failed: the "Location is off" note from the redesign (screen 41) */}
            {isHelp && whereMode === "gps" && gps.kind === "error" ? (
              <div className="ir-gps-off" role="alert">
                <p className="ir-gps-off-title">Location is off</p>
                <p className="ir-gps-off-text">We can&rsquo;t see where you are. You can still pick a spot on the map.</p>
                <div className="ir-gps-off-actions">
                  <button type="button" className="ir-where-btn" onClick={pickOnMap}>
                    <Icon name="pin" size={18} />
                    <span>Pick on map</span>
                  </button>
                  <button type="button" className="ir-where-btn" onClick={findMyLocation}>
                    <span>Try again</span>
                  </button>
                </div>
              </div>
            ) : (
              whereMode === "gps" &&
              gps.text && (
                <p
                  className={`ir-where-msg${gps.kind === "error" ? " ir-where-msg-error" : ""}`}
                  role={gps.kind === "error" ? "alert" : "status"}
                >
                  {gps.text}
                </p>
              )
            )}

            {/* The mini map only exists while "Pick on map" is chosen. The pin is kept if you switch. */}
            {whereMode === "map" && (
              <div className="ir-where-map">
                <LocationPicker value={point} onChange={onPinChange} />
              </div>
            )}
            {errors.location && <p className="ir-error">{errors.location}</p>}
          </div>

          {/* Short note / Details */}
          <div className="ir-field">
            <label className="ir-label" htmlFor="incident-details">
              {isHelp ? "Short note" : "Details"} <span className="ir-hint">(optional)</span>
            </label>
            <textarea
              id="incident-details"
              className="ir-input ir-input-light ir-textarea"
              placeholder={isHelp ? "Grandmother cannot walk, water at the door." : "Water is knee-deep near the school."}
              maxLength={MAX_DETAILS}
              value={form.details}
              onChange={(e) => change("details", e.target.value)}
            />
            <p className="ir-counter" aria-live="off">
              {form.details.length} / {MAX_DETAILS}
            </p>
          </div>
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
          <button type="submit" className={`ir-submit${isHelp ? " ir-submit-help" : ""}`}>
            {isHelp ? "Send for help" : "Send report"}
          </button>
          <p className="ir-footnote">
            {isHelp
              ? "This report goes to responders only. It does not replace calling 911."
              : "Saved on this phone for now. This does not replace calling 911."}
          </p>
        </div>
      </form>
    </section>
  );
}

function CheckMark({ small = false }: { small?: boolean }) {
  const size = small ? 16 : 22;
  return (
    <svg
      className="ir-check"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}