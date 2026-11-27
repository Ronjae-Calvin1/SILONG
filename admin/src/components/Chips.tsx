import type { AdminReport } from "../api/types";

// Chip for the status, or for the hazard state. `phone` shows "Mine" for a report you took.
export default function Chips({ r, phone = false }: { r: AdminReport; phone?: boolean }) {
  const chips: { text: string; tone: string }[] = [];
  if (r.status === "resolved") chips.push({ text: "Resolved", tone: "green" });
  else if (r.status === "false") chips.push({ text: "False", tone: "grey" });
  else {
    if (r.kind === "hazard") {
      if (r.hazard_state === "verified") chips.push({ text: "Verified", tone: "green" });
      else if (r.hazard_state === "unconfirmed") chips.push({ text: "Unconfirmed", tone: "yellow" });
      else chips.push({ text: "Pending", tone: "grey" }); // fewer than 3 phones: not public yet
    }
    if (r.status === "new" && r.kind === "help") chips.push({ text: "New", tone: "red" });
    if (r.status === "being_handled") chips.push({ text: phone && r.is_mine ? "Mine" : "Being handled", tone: "yellow" });
  }
  return (
    <span className="chips">
      {chips.map((c) => (
        <span key={c.text} className={`chip chip-${c.tone}`}>
          {c.text}
        </span>
      ))}
    </span>
  );
}
