import { useEffect, useRef, useState, type CSSProperties } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { api } from "../api/client";
import type { Facility, FacilityStatus, FacilityType } from "../types";
import { TopBar } from "../components/TopBar";
import { ActionRail } from "../components/ActionRail";
import { WeatherStrip } from "../components/WeatherStrip";
import { StatusLegend } from "../components/StatusLegend";
import { AlertsSheet } from "../components/AlertsSheet";
import { IncidentPanel } from "../components/IncidentPanel";
import { EmergencyHotlines } from "../components/EmergencyHotlines";
import { AskSiloPanel } from "../components/AskSiloPanel";
import { FacilityPanel } from "../components/FacilityPanel";
import { SearchBar } from "../components/SearchBar";
import { FilterChips } from "../components/FilterChips";
import { matchesFilter, type FilterId } from "../components/facilityFilter";
import { AddEvacCenter } from "../components/AddEvacCenter";
import { StatusForm } from "../components/StatusForm";
import { HamburgerMenu } from "../components/HamburgerMenu";
import type { MenuPage } from "../components/MenuPages";
import { loadHidden, saveHidden, toHiddenCenter, type HiddenCenter } from "../components/hiddenCenters";
import { rememberMyPlace } from "../components/myActivity";
import { facilityKindLabel, statusKey, withNewStatus } from "../components/statusInfo";
import { pinIconSvg } from "../components/pinIcons";
import { FacilityList } from "../components/FacilityList";
import { MapControls } from "../components/MapControls";
import "../components/MapPins.css";
import "./MapPage.css";
import "./MapDesktop.css";

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
  const [error, setError] = useState<string | null>(null); // Is the "Submit Incident report" panel open? (starts closed)
  const [incidentOpen, setIncidentOpen] = useState(false); // How tall the sheet is right now, so the round buttons can ride above it.
  const [emergencyOpen, setEmergencyOpen] = useState(false);
  const [askOpen, setAskOpen] = useState(false); // Ask Silo panel (right side on desktop, bottom sheet on phones)
  const [sheetH, setSheetH] = useState(0); // Pin that is open in the details panel, and whether its update form is open.
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false); // True when the form was opened from "Set capacity" (capacity field first).
  const [focusCapacity, setFocusCapacity] = useState(false); // Top-bar menu: Map, My reports, My suggested places, Hidden on this phone, About, FAQs, Support, Admin sign in.
  const [menuPage, setMenuPage] = useState<MenuPage | null>(null); // which page the menu shows (null = the menu list itself)
  const [menuOpen, setMenuOpen] = useState(false); // Hidden on this phone: evacuation centers this person hid on this browser only (kept in localStorage).
  const [hidden, setHidden] = useState<HiddenCenter[]>(loadHidden); // "notice" is for messages from the server that change what the person typed (longer, orange).
  const [toast, setToast] = useState<{ text: string; kind: "ok" | "notice" } | null>(null); // True while someone is adding an evacuation center (placing the pin or filling in the form).
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState<FilterId>("all"); // Counters that tell AddEvacCenter / AlertsSheet "start now" (see the rail).
  const [addRequest, setAddRequest] = useState(0);
  const [alertsRequest, setAlertsRequest] = useState(0);
  const [alertsCloseRequest, setAlertsCloseRequest] = useState(0);
  const mapDiv = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const pinsRef = useRef<Map<number, Pin>>(new Map());
  const userMarkerRef = useRef<maplibregl.Marker | null>(null);
  const [userPos, setUserPos] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(false);
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
    // Ask the browser where the user is. Used by the ◎ button and the "nearest first" list.
  function locateMe(moveMap: boolean) {
    if (!("geolocation" in navigator)) {
      showToast("This browser cannot share your location.", "notice", 4000);
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        const p = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setUserPos(p);
        if (moveMap && mapRef.current) {
          mapRef.current.easeTo({
            center: [p.lng, p.lat],
            zoom: Math.max(mapRef.current.getZoom(), 14),
            duration: 600,
          });
        }
      },
      () => {
        setLocating(false);
        if (moveMap) showToast("Could not get your location. Check that location is allowed for this site.", "notice", 5000);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  }

  // If the person already allowed location before, use it quietly (no pop-up on page load).
  useEffect(() => {
    if (!("permissions" in navigator) || !("geolocation" in navigator)) return;
    navigator.permissions
      .query({ name: "geolocation" })
      .then((r) => {
        if (r.state === "granted") locateMe(false);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Blue dot for the user's position.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !userPos) return;
    if (!userMarkerRef.current) {
      const el = document.createElement("div");
      el.className = "user-dot";
      el.setAttribute("aria-label", "Your location");
      userMarkerRef.current = new maplibregl.Marker({ element: el }).setLngLat([userPos.lng, userPos.lat]).addTo(map);
    } else {
      userMarkerRef.current.setLngLat([userPos.lng, userPos.lat]);
    }
  }, [userPos]);

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

  // Centers hidden on this phone are left out of the pins, the search and the list.
  const hiddenIds = new Set(hidden.map((h) => h.id));
  const visible = facilities.filter((f) => !hiddenIds.has(f.id));
  const shown = visible.filter((f) => matchesFilter(f, filter));

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
        el.className = "pin facility-pin";
        el.setAttribute("role", "button");
        el.tabIndex = 0;
        el.setAttribute("aria-label", f.name);

        const body = document.createElement("div");
        body.className = "pin-body";
        const icon = document.createElement("span");
        icon.className = "pin-icon";
        icon.innerHTML = pinIconSvg(f); // fixed icon strings only, no user text
        body.appendChild(icon);
        el.appendChild(body);

        const badge = document.createElement("span");
        badge.className = "pin-badge";
        badge.setAttribute("aria-hidden", "true");
        badge.textContent = TYPE_LETTER[f.type];
        el.appendChild(badge);

        const open = () => {
          setAlertsCloseRequest((n) => n + 1);
          setSelectedId(f.id);
          setFormOpen(false);
          setMenuOpen(false);
        };

        el.addEventListener("click", open);
        el.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            open();
          }
        });

        const marker = new maplibregl.Marker({ element: el, anchor: "center"})
          .setLngLat([f.longitude, f.latitude])
          .addTo(map);
        pin = { marker, el };
        pins.set(f.id, pin);
      }
      pin.el.dataset.status = statusKey(f); // open | almost_full | busy | full | closed | unknown
      pin.el.dataset.outdated = String(!!f.status?.is_outdated);
      pin.el.dataset.source = f.source; // "user" gets a small ring (added through the app)
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facilities, filter, hidden]); // "hidden": hiding or unhiding a center updates the pins right away

  // Highlight the selected pin.
  useEffect(() => {
    pinsRef.current.forEach((pin, id) => {
      pin.el.dataset.selected = String(id === selectedId);
    });
  }, [selectedId, facilities, filter]);

    // If a place gets opened (pin tap or search result), the hotlines panel steps aside.
   // If a place gets opened (pin tap or search result), the other panels step aside.
  useEffect(() => {
    if (selectedId === null) return;
    setEmergencyOpen(false);
    setIncidentOpen(false);
    setAskOpen(false);
    setAlertsCloseRequest((n) => n + 1);
  }, [selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const desktop = window.matchMedia("(min-width: 1024px)").matches;
    const f = facilities.find((x) => x.id === selectedId);
    if (f) {
      hadSelection.current = true;
      map.easeTo({
        center: [f.longitude, f.latitude],
        padding: desktop
          ? { top: 0, left: 0, right: 430, bottom: 0 }
          : { top: 0, left: 0, right: 0, bottom: Math.min(320, window.innerHeight * 0.5) },
        duration: 300,
      });
    } else if (hadSelection.current) {
      hadSelection.current = false;
      map.easeTo({ padding: { top: 0, left: 0, right: 0, bottom: 0 }, duration: 300 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const selected = facilities.find((f) => f.id === selectedId) ?? null;

  // Closes every pop-up except the one you name. Each trigger calls this first,
  // then opens its own panel, so only one panel is ever open at a time.
  function closeOtherPanels(keep?: "emergency" | "incident" | "alerts" | "ask") {
    if (keep !== "emergency") setEmergencyOpen(false);
    if (keep !== "incident") setIncidentOpen(false);
    if (keep !== "ask") setAskOpen(false);
    if (keep !== "alerts") setAlertsCloseRequest((n) => n + 1);
    setSelectedId(null);
    setFormOpen(false);
    setMenuOpen(false);
  }
  
  function closeMenu() {
    setMenuOpen(false);
    setMenuPage(null);
  }

  function showToast(text: string, kind: "ok" | "notice" = "ok", ms = 3000) {
    setToast({ text, kind });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), ms);
  }

  function handleSaved(facilityId: number, saved: FacilityStatus) {
    const { message, ...status } = saved;
    lastSaveAt.current = Date.now();
    setFacilities((list) => list.map((f) => (f.id === facilityId ? withNewStatus(f, status) : f)));
    setFormOpen(false);
    if (message) showToast(message, "notice", 8000);
    else showToast("Status updated. Thank you!");
  }

  // Adding starts: close the details panel and the menu. Adding ends: nothing to undo.
  function handleAddActive(active: boolean) {
    setAdding(active);
    if (active) {
      setAlertsCloseRequest((n) => n + 1);
      setSelectedId(null);
      setFormOpen(false);
      setMenuOpen(false);
    }
  }

  // The server saved a new evacuation center: show its pin right away and open its details.
  // (lastSaveAt makes a refresh that was already on its way not wipe it out.)
  function handleAdded(facility: Facility) {
    lastSaveAt.current = Date.now();
    setFacilities((list) => (list.some((f) => f.id === facility.id) ? list : [...list, facility]));
    setSelectedId(facility.id);
    showToast("Evacuation center added.");
    if (facility.type === "evacuation_center") {
      rememberMyPlace({ id: facility.id, name: facility.name, kind: facilityKindLabel(facility), savedAt: new Date().toISOString() });
    }
  }

  // "Hide on this phone": the pin disappears from this phone only. Nothing is sent to the server.
  function handleHide(facility: Facility) {
    const entry = toHiddenCenter(facility);
    if (!entry) return; // only evacuation centers can be hidden
    const next = [...hidden.filter((h) => h.id !== entry.id), entry];
    setHidden(next);
    setSelectedId(null);
    setFormOpen(false);
    if (saveHidden(next)) showToast("Hidden on this phone. You can show it again from the menu.");
    else showToast("Hidden for now, but this browser could not save it, so it will show again after a reload.", "notice", 6000);
  }

  // "Unhide" in the menu: the pin comes back on the map right away. Only the chosen center changes.
  function handleUnhide(id: number) {
    const next = hidden.filter((h) => h.id !== id);
    setHidden(next);
    if (saveHidden(next)) showToast("Center shown on the map again.");
    else showToast("Center shown again, but this browser could not save the change.", "notice", 6000);
  }

  // A search result was tapped: open that place's details. The effect that
  // watches selectedId already moves the map to it.
  function handleSearchSelect(facility: Facility) {
    setAlertsCloseRequest((n) => n + 1);
    if (!matchesFilter(facility, filter)) setFilter("all"); // make sure its pin is visible
    setSelectedId(facility.id);
    setFormOpen(false);
    setMenuOpen(false);
  }

  // The same actions are reachable from more than one place (top bar, bottom row, weather strip),
  // so each one lives here once.
  function toggleEmergency() {
    closeOtherPanels("emergency");
    setEmergencyOpen((open) => !open); // tap once = open, tap again = close
  }

  function openAlerts() {
    closeOtherPanels("alerts");
    setAlertsRequest((n) => n + 1);
  }

  // The chatbot is not built yet, so this opens a small "coming soon" panel
  // (same drawer / bottom sheet as the other panels) instead of doing nothing.
  function toggleAsk() {
    closeOtherPanels("ask");
    setAskOpen((open) => !open);
  }

  return (
    <div
      className="map-screen"
      data-adding={adding}
      // Desktop only (CSS): a right-hand panel is open, so the map and its controls make room for it.
      data-drawer={emergencyOpen || incidentOpen || askOpen || adding || sheetH > 0}
      style={{ "--sheet-h": `${sheetH}px` } as CSSProperties}
    >
     <div ref={mapDiv} className="map-canvas" />

      <TopBar
        menuOpen={menuOpen}
        onMenuClick={() => {
          if (menuOpen && menuPage === null) {
            closeMenu();
          } else {
            closeOtherPanels(); 
            setMenuPage(null);
            setMenuOpen(true); 
          }
        }}
      />
      
      {!adding && (
        <MapControls
          onZoomIn={() => mapRef.current?.zoomIn()}
          onZoomOut={() => mapRef.current?.zoomOut()}
          onLocate={() => locateMe(true)}
          locating={locating}
        />
      )}

      {!adding && (
        <div className="map-controls">
          {/* Desktop side card only. On phones the title is read by screen readers and the text is hidden. */}
          <div className="map-intro">
            <h1 className="map-intro-title">Find a safe place</h1>
            <p className="map-intro-text">
              Hospitals, clinics and evacuation centers in Batangas City, with the latest reported space and availability.
            </p>
          </div>
          <SearchBar facilities={visible} onSelect={handleSearchSelect} />
          <FilterChips value={filter} onChange={setFilter} />
          <div className="map-side-extra">
            <StatusLegend variant="side" />
            <FacilityList
              facilities={shown}
              origin={userPos ?? { lat: DEFAULT_CENTER[1], lng: DEFAULT_CENTER[0] }}
              hasUserLocation={userPos !== null}
              selectedId={selectedId}
              onSelect={handleSearchSelect}
            />
            <p className="map-note">Official advisories from PAGASA, NDRRMC and the city come first.</p>
          </div>
        </div>
      )}

      {menuOpen && !adding && (
        <HamburgerMenu
          hidden={hidden}
          onUnhide={handleUnhide}
          page={menuPage}
          onPage={setMenuPage}
          onClose={closeMenu}
        />
      )}

      {error && <p className="map-message">Error: {error}</p>}
      {!error && facilities.length > 0 && shown.length === 0 && (
        <p className="map-message">None found in our data. Ask your local DRRMO or call 911.</p>
        )}
        
      {!adding && (
        <div className="dock">
          <StatusLegend variant="map" />
          <WeatherStrip onOpen={openAlerts} />
          <ActionRail
            onOpenEmergency={toggleEmergency}
            onOpenIncident={() => {
              closeOtherPanels("incident");
              setIncidentOpen(true);
            }}
            onOpenBot={toggleAsk}
            onAddCenter={() => {
              closeOtherPanels();
              setAddRequest((n) => n + 1);
            }}
          />
        </div>
      )}

      <AddEvacCenter mapRef={mapRef} onActiveChange={handleAddActive} onAdded={handleAdded} startRequest={addRequest} />

      <AlertsSheet onHeightChange={setSheetH} openRequest={alertsRequest} closeRequest={alertsCloseRequest} />

      <IncidentPanel open={incidentOpen} onClose={() => setIncidentOpen(false)} />
      
      <EmergencyHotlines open={emergencyOpen} facilities={facilities} onClose={() => setEmergencyOpen(false)} />

      <AskSiloPanel open={askOpen} onClose={() => setAskOpen(false)} />

      {selected && !adding && (
        <FacilityPanel
          key={selected.id}
          facility={selected}
          onClose={() => {
            setSelectedId(null);
            setFormOpen(false);
          }}
          onUpdateStatus={() => {
            setFocusCapacity(false);
            setFormOpen(true);
          }}
          onSetCapacity={() => {
            setFocusCapacity(true);
            setFormOpen(true);
          }}
          onHide={handleHide}
        />
      )}

      {selected && formOpen && (
        <StatusForm
          key={`status-form-${selected.id}`}
          facility={selected}
          focusCapacity={focusCapacity}
          onClose={() => setFormOpen(false)}
          onSaved={handleSaved}
        />
      )}

      {toast && (
        <div className="status-toast" data-kind={toast.kind} role="status">
          {toast.text}
        </div>
      )}
    </div>
  );
}