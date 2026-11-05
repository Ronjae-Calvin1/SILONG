import { useEffect, useRef, useState, type CSSProperties } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { api } from "../api/client";
import type { Facility } from "../types";
import { TopBar } from "../components/TopBar";
import { FloatingButtons } from "../components/FloatingButtons";
import { AlertsSheet } from "../components/AlertsSheet";
import { IncidentPanel } from "../components/IncidentPanel";
import "./MapPage.css";

// Base map (vector). Put your MapTiler key and your custom map ID in
// frontend/.env (see .env.example):
//   VITE_MAPTILER_KEY=your_key
//   VITE_MAPTILER_STYLE=your-custom-map-id   (or streets-v2)
// Without a key, the map falls back to plain OpenStreetMap tiles.
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;
const MAPTILER_STYLE = (import.meta.env.VITE_MAPTILER_STYLE as string | undefined) ?? "streets-v2";

const FALLBACK_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const MAP_STYLE: string | maplibregl.StyleSpecification = MAPTILER_KEY
  ? `https://api.maptiler.com/maps/${MAPTILER_STYLE}/style.json?key=${MAPTILER_KEY}`
  : FALLBACK_STYLE;

// Vector maps keep zooming sharply; real detail ends around 22.
const MAX_ZOOM = 22;

// Batangas City (longitude, latitude)
const DEFAULT_CENTER: [number, number] = [121.0583, 13.7565];


export function MapPage() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Is the "Submit Incident report" panel open? (starts closed)
  const [incidentOpen, setIncidentOpen] = useState(false);
  // How tall the sheet is right now, so the round buttons can ride above it.
  const [sheetH, setSheetH] = useState(0);
  const mapDiv = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  useEffect(() => {
    api
      .getFacilities()
      .then(setFacilities)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  // Create the map once.
  useEffect(() => {
    if (!mapDiv.current) return;
    const map = new maplibregl.Map({
      container: mapDiv.current,
      style: MAP_STYLE,
      center: DEFAULT_CENTER,
      zoom: 13,
      maxZoom: MAX_ZOOM,
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // All pins are always shown.
  const shown = facilities;

  // Draw a pin for every facility once the data has loaded.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = shown.map((f) => {
      const box = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = f.name;
      box.appendChild(name);
      box.appendChild(document.createElement("br"));
      box.appendChild(document.createTextNode(f.address ?? ""));
      if (f.contact && f.contact !== "N/A") {
        box.appendChild(document.createElement("br"));
        const a = document.createElement("a");
        a.href = `tel:${f.contact.replace(/[^\d+]/g, "")}`;
        a.textContent = f.contact;
        box.appendChild(a);
      }
      return new maplibregl.Marker()
        .setLngLat([f.longitude, f.latitude])
        .setPopup(new maplibregl.Popup({ offset: 25 }).setDOMContent(box))
        .addTo(map);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facilities]);

  return (
    <div
      className="map-screen"
      style={{ "--sheet-h": `${sheetH}px` } as CSSProperties}
    >
      <div ref={mapDiv} style={{ height: "100%", width: "100%" }} />

      <TopBar />

      {error && <p className="map-message">Error: {error}</p>}

      <FloatingButtons onOpenIncident={() => setIncidentOpen(true)} />

      <AlertsSheet onHeightChange={setSheetH} />

      <IncidentPanel open={incidentOpen} onClose={() => setIncidentOpen(false)} />
    </div>
  );
}