import { FILTERS, type FilterId } from "./facilityFilter";

interface Props {
  value: FilterId; // which chip is selected
  onChange: (id: FilterId) => void;
}

export function FilterChips({ value, onChange }: Props) {
  return (
    <div className="filter-row" role="group" aria-label="Filter places on the map">
      {FILTERS.map((f) => (
        <button
          key={f.id}
          type="button"
          className="filter-btn"
          data-filter={f.id}
          aria-pressed={value === f.id}
          onClick={() => onChange(f.id)}
        >
          {f.id !== "all" && <span className="filter-dot" aria-hidden="true" />}
          {f.label}
        </button>
      ))}
    </div>
  );
}