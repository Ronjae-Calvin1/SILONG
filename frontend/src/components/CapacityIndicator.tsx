import type { Facility } from "../types";
import { capacityLevel, countOf } from "./statusInfo";

interface Props {
  facility: Facility; // an evacuation center
  onSetCapacity: () => void; // opens the update form with the capacity field ready
}

// Capacity part of the details panel for evacuation centers. Three cases:
//   max_capacity and people_inside known -> "85 of 100 people" + bar + "15 spaces left"
//   only max_capacity known              -> "Capacity: 100 people" (also for a new center with no status yet)
//   max_capacity missing                 -> "Capacity not set" + a small button to set it
export function CapacityIndicator({ facility: f, onSetCapacity }: Props) {
  const max = f.max_capacity;
  const people = f.people_inside;

  if (max === null) {
    return (
      <div className="fp-capacity">
        <p className="fp-capacity-plain">
          Capacity not set{" "}
          <button type="button" className="fp-link-btn" onClick={onSetCapacity}>
            Set capacity
          </button>
        </p>
      </div>
    );
  }

  if (people === null) {
    return (
      <div className="fp-capacity">
        <p className="fp-capacity-plain">Capacity: {countOf(max, "person", "people")}</p>
      </div>
    );
  }

  const left = f.spaces_left ?? Math.max(0, max - people);
  const fill = Math.min(100, (people / max) * 100);
  const text = `${people} of ${max} people`;
  const leftText =
    people > max ? "Over capacity" : left === 0 ? "No spaces left" : `${countOf(left, "space", "spaces")} left`;

  return (
    <div className="fp-capacity" data-level={capacityLevel(people, max)} data-outdated={f.is_outdated ? "true" : "false"}>
      <p className="fp-capacity-numbers">
        <strong>{text}</strong>
        <span>{leftText}</span>
      </p>
      <div
        className="fp-capacity-bar"
        role="progressbar"
        aria-label="How full the center is"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={Math.min(people, max)}
        aria-valuetext={`${text}, ${leftText}`}
      >
        <div className="fp-capacity-fill" style={{ width: `${fill}%` }} />
      </div>
    </div>
  );
}

