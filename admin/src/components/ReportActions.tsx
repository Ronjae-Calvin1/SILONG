import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { AdminReport } from "../api/types";
import Dialog from "./Dialog";
import { isOpen, navigateUrl, reference } from "./format";

const RESOLVE_OPTIONS = ["Helped on site", "Moved to a center", "Sent to a hospital", "Could not find them", "Other"];
const FALSE_REASONS = ["Prank or test report", "Duplicate report", "Wrong location", "Could not be reached", "Other"];
const telHref = (n: string) => `tel:${n.replace(/[^\d+*#]/g, "")}`;

type DialogName = "takeover" | "resolve" | "false" | null;

interface Props {
  report: AdminReport;
  onDone: (item: AdminReport) => void; // the server's answer: replace the item with it
  onStale: () => void; // 404 or 409: the list is out of date, refresh it
  bar?: boolean; // phone: the fixed bottom buttons
}

export default function ReportActions({ report: r, onDone, onStale, bar = false }: Props) {
  const [dialog, setDialog] = useState<DialogName>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [option, setOption] = useState(RESOLVE_OPTIONS[0]);
  const [note, setNote] = useState("");
  const [reason, setReason] = useState(FALSE_REASONS[0]);
  const [other, setOther] = useState("");

  if (!isOpen(r)) return null;

  async function run(fn: () => Promise<AdminReport>) {
    setBusy(true);
    setError("");
    try {
      const item = await fn();
      setDialog(null);
      onDone(item);
    } catch (e) {
      // 401 and 403 are handled for the whole console. The rest: show the server's text as written.
      if (e instanceof ApiError) {
        setError(e.detail);
        if (e.status === 404 || e.status === 409) onStale();
      }
    } finally {
      setBusy(false);
    }
  }

  const otherHandler = r.status === "being_handled" && !r.is_mine && r.taken_by;
  const take = () => (otherHandler ? (setError(""), setDialog("takeover")) : run(() => api.take(r.id)));
  const resolveText = note.trim() ? `${option}: ${note.trim()}` : option;
  const falseText = reason === "Other" ? other.trim() : reason;
  const falseOk = falseText.length >= 3 && falseText.length <= 500;
  const close = () => !busy && setDialog(null);
  const ref = reference(r.id);

  return (
    <>
      <div className={bar ? "actions actions-bar" : "actions"}>
        {r.kind === "help" ? (
          <>
            {!(r.status === "being_handled" && r.is_mine) && (
              <button className="btn btn-primary" disabled={busy} onClick={take}>
                Take it
              </button>
            )}
            {r.status === "being_handled" && (
              <button className="btn btn-outline" disabled={busy} onClick={() => run(() => api.release(r.id))}>
                Release
              </button>
            )}
            {!bar && r.contacts[0] && (
              <a className="btn btn-outline" href={telHref(r.contacts[0])}>
                Call
              </a>
            )}
            <a className="btn btn-outline" href={navigateUrl(r)} target="_blank" rel="noopener noreferrer">
              Navigate
            </a>
            <button className="btn btn-green" disabled={busy} onClick={() => (setError(""), setDialog("resolve"))}>
              Resolve
            </button>
          </>
        ) : (
          <>
            {r.hazard_state !== "verified" && (
              <button className="btn btn-green" disabled={busy} onClick={() => run(() => api.verify(r.id))}>
                Verify
              </button>
            )}
            <a className="btn btn-outline" href={navigateUrl(r)} target="_blank" rel="noopener noreferrer">
              Navigate
            </a>
          </>
        )}
        <button className="btn btn-danger" disabled={busy} onClick={() => (setError(""), setDialog("false"))}>
          Mark false
        </button>
      </div>
      {error && !dialog && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}

      {dialog === "takeover" && (
        <Dialog title={`${r.taken_by} is handling this. Take over?`} onClose={close}>
          {error && <p className="action-error">{error}</p>}
          <div className="dialog-buttons">
            <button className="btn btn-outline" onClick={close}>
              Cancel
            </button>
            <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.take(r.id))}>
              Take over
            </button>
          </div>
        </Dialog>
      )}

      {dialog === "resolve" && (
        <Dialog title={`Resolve ${ref}`} onClose={close}>
          <p>What was done? The sender sees “Resolved”.</p>
          <div className="option-row">
            {RESOLVE_OPTIONS.map((o) => (
              <button key={o} type="button" className={o === option ? "pill pill-on" : "pill"} aria-pressed={o === option} onClick={() => setOption(o)}>
                {o}
              </button>
            ))}
          </div>
          <textarea placeholder="Short note for the team (optional)" value={note} maxLength={450} onChange={(e) => setNote(e.target.value)} />
          {error && <p className="action-error">{error}</p>}
          <div className="dialog-buttons">
            <button className="btn btn-outline" onClick={close}>
              Cancel
            </button>
            <button className="btn btn-green" disabled={busy} onClick={() => run(() => api.resolve(r.id, resolveText))}>
              Resolve
            </button>
          </div>
        </Dialog>
      )}

      {dialog === "false" && (
        <Dialog title={`Mark ${ref} as false?`} onClose={close}>
          <p>The sender is not told. After 3 false reports from one phone, that phone is blocked from sending reports.</p>
          <label className="field-label" htmlFor="false-reason">
            Reason (required)
          </label>
          <select id="false-reason" value={reason} onChange={(e) => setReason(e.target.value)}>
            {FALSE_REASONS.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
          {reason === "Other" && (
            <textarea placeholder="Say why (3 to 500 characters)" value={other} maxLength={500} onChange={(e) => setOther(e.target.value)} />
          )}
          {error && <p className="action-error">{error}</p>}
          <div className="dialog-buttons">
            <button className="btn btn-outline" onClick={close}>
              Cancel
            </button>
            <button className="btn btn-primary" disabled={busy || !falseOk} onClick={() => run(() => api.markFalse(r.id, falseText))}>
              Mark false
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
