import type { AdminReport, Place } from "../api/types";
import { distanceText, placeText, timeAgo } from "./format";

const telHref = (n: string) => `tel:${n.replace(/[^\d+*#]/g, "")}`;

// Exact location, contacts and details. For Admins only: the server sends them to nobody else.
export default function ReportDetails({ r, places }: { r: AdminReport; places: Place[] }) {
  const dist = distanceText(r.distance_m);
  return (
    <dl className="details">
      <div>
        <dt>Exact location</dt>
        <dd>{placeText(r, places)}</dd>
      </div>
      {dist && (
        <div>
          <dt>Distance</dt>
          <dd>{dist} from you</dd>
        </div>
      )}
      <div>
        <dt>Sent</dt>
        <dd>{timeAgo(r.created_at)}</dd>
      </div>
      {r.contacts.length > 0 && (
        <div>
          <dt>Contact (Admins only)</dt>
          <dd>
            {r.contacts.map((c) => (
              <span key={c} className="contact">
                {c} <a href={telHref(c)}>Call</a>
              </span>
            ))}
          </dd>
        </div>
      )}
      {r.notes.length > 0 && (
        <div>
          <dt>Details</dt>
          <dd>{r.notes.map((n) => `“${n}”`).join(" ")}</dd>
        </div>
      )}
      {r.kind === "help" && (r.people !== null || r.can_move) && (
        <div>
          <dt>People</dt>
          <dd>
            {r.people ?? "?"}
            {r.can_move ? ` · can move: ${r.can_move}` : ""}
          </dd>
        </div>
      )}
      {r.kind === "hazard" && (
        <div>
          <dt>Reports</dt>
          <dd>
            {r.report_count} from {r.phones} phone{r.phones === 1 ? "" : "s"}
            {r.categories.length > 0 ? ` · ${r.categories.join(", ")}` : ""}
          </dd>
        </div>
      )}
      {r.taken_by && r.status === "being_handled" && (
        <div>
          <dt>Handled by</dt>
          <dd>{r.is_mine ? "You" : r.taken_by}</dd>
        </div>
      )}
      {r.status === "resolved" && (
        <div>
          <dt>Resolved{r.closed_by ? ` by ${r.closed_by}` : ""}</dt>
          <dd>{r.resolution_note ?? "—"}</dd>
        </div>
      )}
      {r.status === "false" && (
        <div>
          <dt>Marked false{r.closed_by ? ` by ${r.closed_by}` : ""}</dt>
          <dd>{r.false_reason ?? "—"}</dd>
        </div>
      )}
    </dl>
  );
}
