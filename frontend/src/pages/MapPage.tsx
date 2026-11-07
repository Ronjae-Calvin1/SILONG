import { useEffect, useRef, useState, type CSSProperties } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { api } from "../api/client";
import type { Facility, FacilityStatus, FacilityType } from "../types";
import { TopBar } from "../components/TopBar";
import { FloatingButtons } from "../components/FloatingButtons";
import { AlertsSheet } from "../components/AlertsSheet";
import { IncidentPanel } from "../components/IncidentPanel";
import { FacilityPanel } from "../components/FacilityPanel";
import { AddEvacCenter } from "../components/AddEvacCenter";
import { StatusForm } from "../components/StatusForm";
import { statusKey } from "../components/statusInfo";
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

// How often the page re-checks the server for new status updates (also keeps
// "May be outdated" honest while the page stays open).
const REFRESH_MS = 60_000;

// Letter shown inside each pin so the facility type stays visible next to the status color.
const TYPE_LETTER: Record<FacilityType, string> = { hospital: "H", clinic: "C", evacuation_center: "E" };

// One pin on the map: the MapLibre marker plus the element we restyle in place.
interface Pin {
  marker: maplibregl.Marker;
  el: HTMLDivElement;
}


export function MapPage() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Is the "Submit Incident report" panel open? (starts closed)
  const [incidentOpen, setIncidentOpen] = useState(false);
  // How tall the sheet is right now, so the round buttons can ride above it.
  const [sheetH, setSheetH] = useState(0);
  // Pin that is open in the details panel, and whether its update form is open.
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  // True while someone is adding an evacuation center (placing the pin or filling in the form).
  const [adding, setAdding] = useState(false);
  const mapDiv = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const pinsRef = useRef<Map<number, Pin>>(new Map());
  const lastSaveAt = useRef(0);
  const hadSelection = useRef(false);
  const toastTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    api
      .getFacilities()
      .then(setFacilities)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  // Pick up other people's updates. A failed refresh is ignored (the pins we
  // already have stay on screen), and a response that was requested before the
  // user's own save is dropped so it cannot overwrite the fresh status.
  useEffect(() => {
    const id = window.setInterval(() => {
      const startedAt = Date.now();
      api
        .getFacilities()
        .then((list) => {
          if (startedAt >= lastSaveAt.current) setFacilities(list);
        })
        .catch(() => {});
    }, REFRESH_MS);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

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

  // Draw a pin for every facility. Pins are created once and then only restyled
  // when a status changes, so an update shows up without redrawing the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const pins = pinsRef.current;
    const ids = new Set(shown.map((f) => f.id));
    pins.forEach((pin, id) => {
      if (!ids.has(id)) {
        pin.marker.remove();
        pins.delete(id);
      }
    });
    shown.forEach((f) => {
      let pin = pins.get(f.id);
      if (!pin) {
        const el = document.createElement("div");
        el.className = "pin";
        el.setAttribute("role", "button");
        el.tabIndex = 0;
        el.setAttribute("aria-label", f.name);
        const body = document.createElement("div");
        body.className = "pin-body";
        const letter = document.createElement("span");
        letter.className = "pin-letter";
        letter.textContent = TYPE_LETTER[f.type];
        body.appendChild(letter);
        el.appendChild(body);
        el.addEventListener("click", () => {
          setSelectedId(f.id);
          setFormOpen(false);
        });
        el.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setSelectedId(f.id);
            setFormOpen(false);
          }
        });
        // The rotated teardrop's tip sits about 20px below the element's center.
        const marker = new maplibregl.Marker({ element: el, anchor: "center", offset: [0, -20] })
          .setLngLat([f.longitude, f.latitude])
          .addTo(map);
        pin = { marker, el };
        pins.set(f.id, pin);
      }
      pin.el.dataset.status = statusKey(f); // open | almost_full | busy | full | closed | unknown
      pin.el.dataset.outdated = String(!!f.status?.is_outdated);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facilities]);

  // Highlight the selected pin.
  useEffect(() => {
    pinsRef.current.forEach((pin, id) => {
      pin.el.dataset.selected = String(id === selectedId);
    });
  }, [selectedId, facilities]);

  // Keep the selected pin visible above the details panel.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const f = facilities.find((x) => x.id === selectedId);
    if (f) {
      hadSelection.current = true;
      map.easeTo({
        center: [f.longitude, f.latitude],
        padding: { top: 0, left: 0, right: 0, bottom: Math.min(320, window.innerHeight * 0.5) },
        duration: 300,
      });
    } else if (hadSelection.current) {
      hadSelection.current = false;
      map.easeTo({ padding: { top: 0, left: 0, right: 0, bottom: 0 }, duration: 300 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const selected = facilities.find((f) => f.id === selectedId) ?? null;

  function showToast(message: string) {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3000);
  }

  // The server accepted a new status: show it on the pin and in the panel right away.
  function handleSaved(facilityId: number, status: FacilityStatus) {
    lastSaveAt.current = Date.now();
    setFacilities((list) => list.map((f) => (f.id === facilityId ? { ...f, status } : f)));
    setFormOpen(false);
    showToast("Status updated. Thank you!");
  }

  // Adding starts: close the details panel. Adding ends: nothing to undo.
  function handleAddActive(active: boolean) {
    setAdding(active);
    if (active) {
      setSelectedId(null);
      setFormOpen(false);
    }
  }

  // The server saved a new evacuation center: show its pin right away and open its details.
  // (lastSaveAt makes a refresh that was already on its way not wipe it out.)
  function handleAdded(facility: Facility) {
    lastSaveAt.current = Date.now();
    setFacilities((list) => (list.some((f) => f.id === facility.id) ? list : [...list, facility]));
    setSelectedId(facility.id);
    showToast("Evacuation center added.");
  }

  // The server hid an evacuation center: its pin disappears right away.
  function handleRemoved(facilityId: number) {
    lastSaveAt.current = Date.now();
    setFacilities((list) => list.filter((f) => f.id !== facilityId));
    setSelectedId(null);
    setFormOpen(false);
    showToast("Evacuation center removed.");
  }

  return (
    <div
      className="map-screen"
      data-adding={adding}
      style={{ "--sheet-h": `${sheetH}px` } as CSSProperties}
    >
      <div ref={mapDiv} style={{ height: "100%", width: "100%" }} />

      <TopBar />

      {error && <p className="map-message">Error: {error}</p>}

      <FloatingButtons onOpenIncident={() => setIncidentOpen(true)} />

      <AddEvacCenter mapRef={mapRef} onActiveChange={handleAddActive} onAdded={handleAdded} />

      <AlertsSheet onHeightChange={setSheetH} />

      <IncidentPanel open={incidentOpen} onClose={() => setIncidentOpen(false)} />

      {selected && !adding && (
        <FacilityPanel
          key={selected.id}
          facility={selected}
          onClose={() => {
            setSelectedId(null);
            setFormOpen(false);
          }}
          onUpdateStatus={() => setFormOpen(true)}
          onRemoved={handleRemoved}
        />
      )}

      {selected && formOpen && (
        <StatusForm
          key={selected.id}
          facility={selected}
          onClose={() => setFormOpen(false)}
          onSaved={handleSaved}
        />
      )}

      {toast && (
        <div className="status-toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}