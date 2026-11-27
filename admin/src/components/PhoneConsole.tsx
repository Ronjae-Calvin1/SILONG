import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AdminReport, ContactSettings, Place } from "../api/types";
import { useAuth } from "../auth";
import logo from "../assets/silong-logo-white.png";
import Chips from "./Chips";
import LiveMap, { type Layers } from "./LiveMap";
import ReportActions from "./ReportActions";
import ReportCard from "./ReportCard";
import ReportDetails from "./ReportDetails";
import { distanceText, placeText, reportTitle } from "./format";
import { useReports, type Filter } from "./useReports";

type Tab = "reports" | "map" | "me";
const FILTERS: { id: Filter; label: string }[] = [
  { id: "new", label: "New" },
  { id: "mine", label: "Mine" },
  { id: "handling", label: "Handling" },
  { id: "resolved", label: "Resolved" },
];

export default function PhoneConsole() {
  const { user, signOut } = useAuth();
  const [tab, setTab] = useState<Tab>("reports");
  const [filter, setFilter] = useState<Filter>("new");
  const [detailId, setDetailId] = useState<number | null>(null);
  const [mapSelected, setMapSelected] = useState<number | null>(null);
  const [layers, setLayers] = useState<Layers>({ reports: true, hazards: true, places: true, resolved: false });
  const [places, setPlaces] = useState<Place[]>([]);
  const [position, setPosition] = useState<{ latitude: number; longitude: number } | null>(null);
  const [shownAlertId, setShownAlertId] = useState<number | null>(null); // the alert already opened or closed
  const [contact, setContact] = useState<ContactSettings | null>(null);

  // The map tab always shows open reports.
  const listFilter: Filter = tab === "map" ? "all" : filter;
  const { items, loaded, summary, newHelp, error, apply, refresh } = useReports(listFilter, position);

  useEffect(() => {
    api.getPlaces().then(setPlaces).catch(() => undefined);
  }, []);

  // Send the Admin's position (for distance) only when the browser allows it.
  useEffect(() => {
    if (!("geolocation" in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      (p) => setPosition({ latitude: Number(p.coords.latitude.toFixed(4)), longitude: Number(p.coords.longitude.toFixed(4)) }),
      () => undefined,
      { maximumAge: 60_000, timeout: 10_000 },
    );
  }, []);

  useEffect(() => {
    if (tab !== "me") return;
    api.getContactSettings().then(setContact).catch(() => setContact(null));
  }, [tab]);

  const detail: AdminReport | undefined = items.find((r) => r.id === detailId);
  const mapReport = items.find((r) => r.id === mapSelected);
  const showAlert = newHelp !== null && newHelp.id !== shownAlertId;

  function openAlert() {
    if (!newHelp) return;
    setShownAlertId(newHelp.id);
    setTab("reports");
    setFilter("new");
    setDetailId(newHelp.id);
  }

  const counts: Record<string, number | null> = {
    new: summary?.new_reports ?? null,
    mine: summary?.mine ?? null,
    handling: summary?.being_handled ?? null,
    resolved: null,
  };

  return (
    <div className="phone">
      <header className="phone-head">
        <img src={logo} alt="SILONG" />
        <span className="badge-admin">ADMIN</span>
        <span className="topbar-name">{user?.name}</span>
      </header>

      {showAlert && newHelp && (
        <div className="alert-red alert-phone" role="alert">
          <div>
            <strong>New: Needs help</strong>
            <span>
              {placeText(newHelp, places)}
              {distanceText(newHelp.distance_m) ? ` · ${distanceText(newHelp.distance_m)}` : ""} · just now
            </span>
          </div>
          <button className="btn btn-white" onClick={openAlert}>
            Open
          </button>
        </div>
      )}

      <main className="phone-main">
        {error && (
          <div className="notice-error" role="alert">
            {error.detail}{" "}
            <button className="link-btn" onClick={refresh}>
              Try again
            </button>
          </div>
        )}

        {tab === "reports" && detail && (
          <section className="phone-detail">
            <button className="link-btn back" onClick={() => setDetailId(null)}>
              ← Back to reports
            </button>
            <LiveMap compact reports={[detail]} places={[]} layers={{ reports: true, hazards: true, resolved: true, places: false }} selectedId={detail.id} onSelect={() => undefined} />
            <div className="phone-detail-body">
              <div className="card-top">
                <span className={`card-kind kind-${detail.kind}`}>{detail.kind === "help" ? "Needs help" : "Hazard"}</span>
                <Chips r={detail} phone />
              </div>
              <h1>{reportTitle(detail)}</h1>
              <ReportDetails r={detail} places={places} />
            </div>
            <ReportActions report={detail} onDone={apply} onStale={refresh} bar />
          </section>
        )}

        {tab === "reports" && !detail && (
          <>
            <div className="chip-row" role="group" aria-label="Filter reports">
              {FILTERS.map((f) => (
                <button key={f.id} className={f.id === filter ? "pill pill-on" : "pill"} aria-pressed={f.id === filter} onClick={() => setFilter(f.id)}>
                  {f.label}
                  {counts[f.id] !== null ? ` ${counts[f.id]}` : ""}
                </button>
              ))}
            </div>
            <p className="live-sub">Most urgent first</p>
            <div className="cards">
              {items.map((r) => (
                <ReportCard key={r.id} report={r} places={places} phone onSelect={() => setDetailId(r.id)} />
              ))}
              {loaded && items.length === 0 && !error && <p className="empty">No reports here right now.</p>}
              {!loaded && !error && <p className="empty">Loading…</p>}
            </div>
          </>
        )}

        {tab === "map" && (
          <section className="phone-map">
            <div className="layer-row" role="group" aria-label="Map layers">
              {(["reports", "hazards", "places"] as const).map((k) => (
                <button key={k} className={layers[k] ? "pill pill-dark" : "pill"} aria-pressed={layers[k]} onClick={() => setLayers((s) => ({ ...s, [k]: !s[k] }))}>
                  {k[0].toUpperCase() + k.slice(1)}
                </button>
              ))}
            </div>
            <LiveMap reports={items} places={places} layers={layers} selectedId={mapSelected} onSelect={setMapSelected} />
            {mapReport && (
              <div className="map-card">
                <div className="card-top">
                  <span className={`card-kind kind-${mapReport.kind}`}>{mapReport.kind === "help" ? "Needs help" : "Hazard"}</span>
                  <Chips r={mapReport} phone />
                </div>
                <strong className="card-title">{reportTitle(mapReport)}</strong>
                <div className="actions">
                  <ReportActions report={mapReport} onDone={apply} onStale={refresh} />
                  <button className="btn btn-outline" onClick={() => (setDetailId(mapReport.id), setTab("reports"))}>
                    Open
                  </button>
                </div>
              </div>
            )}
          </section>
        )}

        {tab === "me" && (
          <section className="phone-me">
            <div className="me-card">
              <strong>{user?.name}</strong>
            </div>
            <div className="me-card">
              <strong>Signs out by itself</strong>
              <span>After {user?.idle_timeout_minutes ?? 30} minutes without use</span>
            </div>
            <div className="me-card">
              <strong>Call the control room</strong>
              {contact === null ? (
                <span>…</span>
              ) : contact.control_room_number ? (
                <a className="btn btn-outline" href={`tel:${contact.control_room_number.replace(/[^\d+*#]/g, "")}`}>
                  {contact.control_room_number}
                </a>
              ) : (
                <span>Number not set yet</span>
              )}
            </div>
            <button className="btn btn-danger me-signout" onClick={signOut}>
              Sign out
            </button>
            <p className="live-sub">Accounts, emergency numbers, advisories and the chatbot guide are managed by an Admin on a computer.</p>
          </section>
        )}
      </main>

      <nav className="phone-nav" aria-label="Admin sections">
        <button className={tab === "reports" ? "on" : ""} onClick={() => (setTab("reports"), setDetailId(null))}>
          Reports{summary && summary.new_reports > 0 ? <em>{summary.new_reports}</em> : null}
        </button>
        <button className={tab === "map" ? "on" : ""} onClick={() => setTab("map")}>
          Map
        </button>
        <button className={tab === "me" ? "on" : ""} onClick={() => setTab("me")}>
          Me
        </button>
      </nav>
    </div>
  );
}
