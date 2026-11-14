import { useEffect, useRef, useState } from "react";
import { Icon } from "./icons";
import type { Facility } from "../types";
import { CATEGORIES, NATIONAL_HOTLINES, buildLocalHotlines, type HotlineCategory } from "./hotlineData";
import "./EmergencyHotlines.css";
import "./PanelUpdates.css";

type Props = {
  open: boolean;
  facilities: Facility[];
  onClose: () => void;
};


// Copies text to the clipboard. Returns true if it worked.
// navigator.clipboard needs a secure page (https or localhost); the fallback covers older browsers.
async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the fallback below
  }
  try {
    const box = document.createElement("textarea");
    box.value = text;
    box.setAttribute("readonly", "");
    box.style.position = "fixed";
    box.style.opacity = "0";
    document.body.appendChild(box);
    box.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(box);
    return ok;
  } catch {
    return false;
  }
}

function CopyIcon({ copied }: { copied: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {copied ? (
        <path d="M5 12.5l4.5 4.5L19 7.5" />
      ) : (
        <>
          <rect x="9" y="9" width="11" height="11" rx="2" />
          <path d="M5 15V6a2 2 0 012-2h9" />
        </>
      )}
    </svg>
  );
}

export function EmergencyHotlines({ open, facilities, onClose }: Props) {
  // Which category chip is selected (starts on "All").
  const [category, setCategory] = useState<HotlineCategory>("all");
  const closeRef = useRef<HTMLButtonElement>(null);
  // Which number was just copied (turns its button into a check mark) and the message shown at the bottom.
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [toast, setToast] = useState<{ text: string; kind: "ok" | "error" } | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  async function copyNumber(key: string, text: string) {
    const ok = await copyToClipboard(text);
    setCopiedKey(ok ? key : null);
    setToast(
      ok
        ? { text: `Copied ${text}`, kind: "ok" }
        : { text: "Couldn't copy. Please press and hold the number to copy it.", kind: "error" }
    );
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => {
      setCopiedKey(null);
      setToast(null);
    }, 2500);
  }

    // When the panel opens, move keyboard focus to the close button.
  useEffect(() => {
    if (open) closeRef.current?.focus({ preventScroll: true });
  }, [open]);

  // The Escape key closes the panel (only while it is open).
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const local = buildLocalHotlines(facilities);
  const shown = local.filter((h) => category === "all" || h.categories.includes(category));
  const categoryLabel = CATEGORIES.find((c) => c.id === category)?.label ?? "";

  return (
    <section
      className={`eh-panel${open ? " eh-panel-open" : ""}`}
      role="dialog"
      aria-labelledby="eh-title"
      inert={!open}>
      <div className="eh-top">
        <button type="button" className="eh-handle-btn" aria-label="Close emergency hotlines" onClick={onClose}>
          <span className="eh-handle" aria-hidden="true" />
        </button>
        <header className="eh-header">
          <h2 className="eh-title" id="eh-title">
            Emergency Hotlines
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="eh-close"
            aria-label="Close emergency hotlines"
            onClick={onClose}
          >
            <Icon name="close" />
          </button>
        </header>
      </div>

      <div className="eh-scroll">
        <p className="eh-note">
          <Icon name="warning" size={18} />
          <span>In case of an emergency, contact the appropriate hotline for immediate assistance.</span>
        </p>

        {/* National numbers: always visible, one tap to call. */}
        <ul className="eh-national">
          {NATIONAL_HOTLINES.map((h) => (
            <li className="eh-national-card" key={h.number}>
              <div>
                <p className="eh-number">{h.number}</p>
                <p className="eh-org">{h.name}</p>
              </div>
              <div className="eh-actions">
                <a className="eh-call-now" href={`tel:${h.number}`} aria-label={`Call ${h.name} at ${h.number}`}>
                  <Icon name="phone" size={20} />
                  <span>Call Now</span>
                </a>
                <button
                  type="button"
                  className="eh-copy"
                  data-copied={copiedKey === `national-${h.number}`}
                  aria-label={`Copy ${h.name} number ${h.number}`}
                  onClick={() => copyNumber(`national-${h.number}`, h.number)}
                >
                  <CopyIcon copied={copiedKey === `national-${h.number}`} />
                </button>
              </div>
            </li>
          ))}
        </ul>

        <h3 className="eh-subtitle" id="eh-cat-title">
          What's your emergency?
        </h3>
        <div className="eh-chips" role="group" aria-labelledby="eh-cat-title">
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              type="button"
              className="eh-chip"
              aria-pressed={category === c.id}
              onClick={() => setCategory(c.id)}
            >
              {c.label}
            </button>
          ))}
        </div>

        {shown.length > 0 ? (
          <ul className="eh-list">
            {shown.map((h) => (
              <li className="eh-card" key={h.id}>
                <div className="eh-card-head">
                  <div>
                    <h4 className="eh-card-name">{h.name}</h4>
                    <p className="eh-card-desc">{h.description}</p>
                  </div>
                  <span className="eh-tag">{h.tag}</span>
                </div>
                <ul className="eh-phones">
                  {h.phones.map((p, i) => (
                    <li className="eh-phone-row" key={i}>
                      <span className="eh-phone-text">{p.text}</span>
                      <div className="eh-actions">
                        <a className="eh-call" href={p.href} aria-label={`Call ${h.name} at ${p.text}`}>
                          <Icon name="phone" size={18} />
                          <span>Call</span>
                        </a>
                        <button
                          type="button"
                          className="eh-copy"
                          data-copied={copiedKey === `${h.id}-${i}`}
                          aria-label={`Copy ${h.name} number ${p.text}`}
                          onClick={() => copyNumber(`${h.id}-${i}`, p.text)}
                        >
                          <CopyIcon copied={copiedKey === `${h.id}-${i}`} />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        ) : (
          <p className="eh-empty" role="status">
            {category === "all"
              ? "No local emergency numbers are available right now."
              : `No local ${categoryLabel.toLowerCase()} numbers are available in our data.`}{" "}
            Call 911 above, or ask your barangay or local DRRMO.
          </p>
        )}
      </div>

      {/* Short message after copying. role="status" lets screen readers announce it. */}
      {toast && (
        <p className="eh-toast" data-kind={toast.kind} role="status">
          {toast.text}
        </p>
      )}
    </section>
  );
}