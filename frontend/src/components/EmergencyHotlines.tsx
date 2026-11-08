import { useEffect, useRef, useState } from "react";
import { Icon } from "./icons";
import type { Facility } from "../types";
import { CATEGORIES, NATIONAL_HOTLINES, buildLocalHotlines, type HotlineCategory } from "./hotlineData";
import "./EmergencyHotlines.css";

type Props = {
  facilities: Facility[];
  onClose: () => void;
};

export function EmergencyHotlines({ facilities, onClose }: Props) {
  // Which category chip is selected (starts on "All").
  const [category, setCategory] = useState<HotlineCategory>("all");
  const closeRef = useRef<HTMLButtonElement>(null);

  // Move keyboard focus to the close button when the panel opens.
  useEffect(() => {
    closeRef.current?.focus({ preventScroll: true });
  }, []);

  // The Escape key closes the panel.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const local = buildLocalHotlines(facilities);
  const shown = local.filter((h) => category === "all" || h.categories.includes(category));
  const categoryLabel = CATEGORIES.find((c) => c.id === category)?.label ?? "";

  return (
    <section className="eh-panel" role="dialog" aria-labelledby="eh-title">
      <div className="eh-top">
        <span className="eh-handle" aria-hidden="true" />
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
              <a className="eh-call-now" href={`tel:${h.number}`} aria-label={`Call ${h.name} at ${h.number}`}>
                <Icon name="phone" size={20} />
                <span>Call Now</span>
              </a>
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
                      <a className="eh-call" href={p.href} aria-label={`Call ${h.name} at ${p.text}`}>
                        <Icon name="phone" size={18} />
                        <span>Call</span>
                      </a>
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
    </section>
  );
}