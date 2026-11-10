import { useEffect, useRef, useState } from "react";
import type { Facility } from "../types";
import { Icon } from "./icons";
import { typeLabel } from "./facilityFilter";

interface Props {
  facilities: Facility[]; // everything loaded, not only what the chips show
  onSelect: (facility: Facility) => void;
}

const MAX_RESULTS = 5;

export function SearchBar({ facilities, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false); // is the results list showing?
  const wrapRef = useRef<HTMLDivElement>(null);

  // Tapping anywhere outside the search area closes the results list.
  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  const text = query.trim().toLowerCase();
  const results = text
    ? facilities
        .filter((f) => f.name.toLowerCase().includes(text) || (f.address ?? "").toLowerCase().includes(text))
        .slice(0, MAX_RESULTS)
    : [];

  function choose(f: Facility) {
    onSelect(f);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className="search" ref={wrapRef}>
      <div className="search-field">
        <span className="search-icon">
          <Icon name="search" size="var(--icon-sm)" />
        </span>
        <input
          className="search-input"
          type="text"
          inputMode="search"
          autoComplete="off"
          placeholder="Search a place or barangay"
          aria-label="Search a place or barangay"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
        />
        {query && (
          <button type="button" className="search-clear" aria-label="Clear search" onClick={() => setQuery("")}>
            <Icon name="close" size="var(--icon-xs)" />
          </button>
        )}
      </div>

      {open && text && (
        <ul className="search-results">
          {results.length === 0 ? (
            <li className="search-empty">No matching places in our data.</li>
          ) : (
            results.map((f) => (
              <li key={f.id}>
                <button type="button" className="search-result" onClick={() => choose(f)}>
                  <span className="search-result-name">{f.name}</span>
                  <span className="search-result-meta">
                    {typeLabel(f)}
                    {f.address ? ` · ${f.address}` : ""}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}