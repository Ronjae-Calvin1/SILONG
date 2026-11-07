import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Facility, RemovedCenter } from "../types";
import { Icon } from "./icons";
import { timeAgo } from "./statusInfo";
import "./EvacManager.css";

interface Props {
  onClose: () => void;
  // The server brought a center back; the page shows its pin again.
  onRestored: (facility: Facility) => void;
}

function messageOf(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
}

// Small list under the top-bar menu button: centers that were removed from the map (soft
// delete, nothing is erased), each with a Restore button. It is only mounted while the menu is
// open, so the list is fetched fresh every time it opens.
export function RemovedCenters({ onClose, onRestored }: Props) {
  const [centers, setCenters] = useState<RemovedCenter[] | null>(null); // null = loading
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0); // bump to load again
  const [restoringId, setRestoringId] = useState<number | null>(null);
  const [rowError, setRowError] = useState<{ id: number; text: string } | null>(null);
  const [now] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    api
      .getRemovedCenters()
      .then((list) => {
        if (!cancelled) setCenters(list);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(messageOf(err));
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function reload() {
    setLoadError(null);
    setCenters(null);
    setAttempt((n) => n + 1);
  }

  async function restore(c: RemovedCenter) {
    if (restoringId !== null) return;
    setRestoringId(c.id);
    setRowError(null);
    try {
      const facility = await api.restoreEvacuationCenter(c.id);
      setCenters((list) => (list ? list.filter((x) => x.id !== c.id) : list));
      onRestored(facility); // the page shows the pin right away and closes this list
    } catch (err) {
      // The center stays in the list so it can be tried again.
      setRowError({ id: c.id, text: messageOf(err) });
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <section className="removed-menu" aria-label="Removed evacuation centers">
      <header className="removed-header">
        <h2 className="removed-title">Removed centers</h2>
        <button type="button" className="removed-close" onClick={onClose} aria-label="Close removed centers">
          <Icon name="close" size={20} />
        </button>
      </header>

      {loadError ? (
        <div className="removed-body">
          <p className="status-form-error" role="alert">
            {loadError}
          </p>
          <button type="button" className="removed-restore-btn" onClick={reload}>
            Try again
          </button>
        </div>
      ) : centers === null ? (
        <p className="removed-note">Loading…</p>
      ) : centers.length === 0 ? (
        <p className="removed-note">No removed evacuation centers.</p>
      ) : (
        <>
          <p className="removed-note">Hidden from the map, not deleted. Restore one to show it again.</p>
          <ul className="removed-list">
            {centers.map((c) => (
              <li className="removed-item" key={c.id}>
                <div className="removed-info">
                  <span className="removed-name">{c.name}</span>
                  <span className="removed-when">Removed {timeAgo(c.removed_at, now)}</span>
                </div>
                <button
                  type="button"
                  className="removed-restore-btn"
                  disabled={restoringId !== null}
                  onClick={() => restore(c)}
                >
                  {restoringId === c.id ? "Restoring…" : rowError?.id === c.id ? "Try again" : "Restore"}
                </button>
                {rowError?.id === c.id && (
                  <p className="status-form-error removed-error" role="alert">
                    {rowError.text}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
