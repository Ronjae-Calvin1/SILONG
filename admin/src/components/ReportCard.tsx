import { useEffect, useRef, type ReactNode } from "react";
import type { AdminReport, Place } from "../api/types";
import Chips from "./Chips";
import { distanceText, placeText, reportTitle, timeAgo } from "./format";

interface Props {
  report: AdminReport;
  places: Place[];
  selected?: boolean;
  phone?: boolean;
  onSelect: () => void;
  children?: ReactNode; // desktop: the details and actions of the selected card
}

export default function ReportCard({ report: r, places, selected = false, phone = false, onSelect, children }: Props) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  const dist = distanceText(r.distance_m);
  const closed = r.status === "resolved" || r.status === "false";
  return (
    <article ref={ref} className={`card card-${r.kind}${selected ? " card-selected" : ""}${closed ? " card-closed" : ""}`}>
      <button type="button" className="card-head" onClick={onSelect} aria-expanded={selected}>
        <span className="card-top">
          <span className={`card-kind kind-${r.kind}`}>{r.kind === "help" ? "Needs help" : "Hazard"}</span>
          <Chips r={r} phone={phone} />
        </span>
        <strong className="card-title">{reportTitle(r)}</strong>
        <span className="card-place">
          {placeText(r, places)}
          {dist ? ` · ${dist}` : ""} · {timeAgo(r.created_at)}
        </span>
      </button>
      {selected && children}
    </article>
  );
}
