import { useEffect, useState, type CSSProperties } from "react";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { api } from "../api/client";
import type { Facility } from "../types";
import { TopBar } from "../components/TopBar";
import { FloatingButtons } from "../components/FloatingButtons";
import { AlertsSheet } from "../components/AlertsSheet";
import { IncidentPanel } from "../components/IncidentPanel";
import "./MapPage.css";

// Leaflet's default marker icons reference image files by relative path,
// which breaks under bundlers like Vite. Point them at a CDN instead.
const defaultIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});
L.Marker.prototype.options.icon = defaultIcon;

// Batangas City
const DEFAULT_CENTER: [number, number] = [13.7565, 121.0583];

type FacilityType = Facility["type"];

const TYPE_LABELS: Record<FacilityType, string> = {
  hospital: "Hospitals",
  clinic: "Clinics",
  evacuation_center: "Evacuation centers",
};

export function MapPage() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Map starts clean: no pins until the user turns a category on.
  // To show a category by default, add it here, e.g. new Set(["hospital"]).
  const [visible, setVisible] = useState<Set<FacilityType>>(new Set());
  // Is the "Submit Incident report" panel open? (starts closed)
  const [incidentOpen, setIncidentOpen] = useState(false);
  // How tall the sheet is right now, so the round buttons can ride above it.
  const [sheetH, setSheetH] = useState(0);

  useEffect(() => {
    api
      .getFacilities()
      .then(setFacilities)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  function toggle(type: FacilityType) {
    setVisible((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }

  const shown = facilities.filter((f) => visible.has(f.type));

  return (
    <div
      className="map-screen"
      style={{ "--sheet-h": `${sheetH}px` } as CSSProperties}
    >
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={13}
        zoomControl={false}
        style={{ height: "100%", width: "100%" }}
      >
        {/* The old map (OpenStreetMap) */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {shown.map((f) => (
          <Marker key={f.id} position={[f.latitude, f.longitude]}>
            <Popup>
              <strong>{f.name}</strong>
              <br />
              {f.address}
              {f.contact && f.contact !== "N/A" && (
                <>
                  <br />
                  <a href={`tel:${f.contact.replace(/[^\d+]/g, "")}`}>{f.contact}</a>
                </>
              )}
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      <TopBar />

      {/* Category filters: big, tap-friendly buttons */}
      <div className="filter-row">
        {(Object.keys(TYPE_LABELS) as FacilityType[]).map((type) => {
          const count = facilities.filter((f) => f.type === type).length;
          return (
            <button
              key={type}
              className="filter-btn"
              onClick={() => toggle(type)}
              disabled={count === 0}
              aria-pressed={visible.has(type)}
            >
              {visible.has(type) ? "✓ " : ""}
              {TYPE_LABELS[type]} ({count})
            </button>
          );
        })}
      </div>

      {error && <p className="map-message">Error: {error}</p>}
      {!error && visible.size === 0 && facilities.length > 0 && (
        <p className="map-message">Select a category above to show pins on the map.</p>
      )}

      <FloatingButtons onOpenIncident={() => setIncidentOpen(true)} />

      <AlertsSheet onHeightChange={setSheetH} />

      <IncidentPanel open={incidentOpen} onClose={() => setIncidentOpen(false)} />
    </div>
  );
}