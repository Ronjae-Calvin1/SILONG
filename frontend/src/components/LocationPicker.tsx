import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { MAP_STYLE, DEFAULT_CENTER } from "./mapStyle";
import "./LocationPicker.css";

export type Point = { lat: number; lng: number };

type Props = {
  value: Point | null; // the pin (null = no pin yet)
  onChange: (p: Point | null) => void;
};

type GpsState = { kind: "idle" | "busy" | "ok" | "error"; text: string };

/* Mini map for the incident report: tap the map, drag the pin, or press "Use my GPS". */
export function LocationPicker({ value, onChange }: Props) {
  const divRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange; // always the latest function, without recreating the map
  const [gps, setGps] = useState<GpsState>({ kind: "idle", text: "" });

  // The one place that puts or moves the pin.
  function putPin(p: Point, notify = true) {
    const map = mapRef.current;
    if (!map) return;
    const existing = markerRef.current;
    if (existing) {
      existing.setLngLat([p.lng, p.lat]);
    } else {
      const created = new maplibregl.Marker({ color: "#c62222", draggable: true })
        .setLngLat([p.lng, p.lat])
        .addTo(map);
      created.on("dragend", () => {
        const at = created.getLngLat();
        onChangeRef.current({ lat: at.lat, lng: at.lng });
      });
      markerRef.current = created;
    }
    if (notify) onChangeRef.current(p);
  }

  // Create the mini map once.
  useEffect(() => {
    if (!divRef.current) return;
    const map = new maplibregl.Map({
      container: divRef.current,
      style: MAP_STYLE,
      center: value ? [value.lng, value.lat] : DEFAULT_CENTER,
      zoom: value ? 16 : 13,
      maxZoom: 22,
      // On a phone, one finger scrolls the form and two fingers move the map.
      cooperativeGestures: true,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    mapRef.current = map;

    if (value) putPin(value, false);

    map.on("click", (e) => {
      // A tap on the pin itself must not make it jump.
      if (markerRef.current?.getElement().contains(e.originalEvent.target as Node)) return;
      putPin({ lat: e.lngLat.lat, lng: e.lngLat.lng });
      setGps({ kind: "idle", text: "" });
    });

    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The panel slides in, so the map box changes size. Tell the map when that happens.
  useEffect(() => {
    const el = divRef.current;
    if (!el || !("ResizeObserver" in window)) return;
    const ro = new ResizeObserver(() => mapRef.current?.resize());
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // If the parent clears the location (after a successful submit), remove the pin too.
  useEffect(() => {
    if (!value) {
      markerRef.current?.remove();
      markerRef.current = null;
    }
  }, [value]);

  function findMe() {
    if (!("geolocation" in navigator)) {
      setGps({ kind: "error", text: "This browser can't share your location. Tap the map to place the pin." });
      return;
    }
    setGps({ kind: "busy", text: "Finding your location…" });
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const p = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        putPin(p);
        mapRef.current?.flyTo({ center: [p.lng, p.lat], zoom: 16 });
        setGps({
          kind: "ok",
          text: `Location found (about ${Math.round(pos.coords.accuracy)} m accuracy). Drag the pin if it is off.`,
        });
      },
      (err) => {
        let text = "Could not get your location. Tap the map to place the pin.";
        if (err.code === err.PERMISSION_DENIED) {
          text = "Location is turned off for this site. Allow it in your browser settings, or tap the map to place the pin.";
        } else if (err.code === err.TIMEOUT) {
          text = "Finding your location took too long. Try again, or tap the map to place the pin.";
        }
        setGps({ kind: "error", text });
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  }

  function clearPin() {
    markerRef.current?.remove();
    markerRef.current = null;
    onChangeRef.current(null);
    setGps({ kind: "idle", text: "" });
  }

  return (
    <div className="lp">
      <div className="lp-bar">
        <p className="ir-label lp-title">
          Location <span className="ir-hint">pin or description required</span>
        </p>
        <button type="button" className="lp-gps" onClick={findMe} disabled={gps.kind === "busy"}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
          </svg>
          {gps.kind === "busy" ? "Locating…" : "Use my GPS"}
        </button>
      </div>

      <div ref={divRef} className="lp-map" role="application" aria-label="Map. Tap to place a pin at the incident location." />

      {gps.text && (
        <p className={`lp-msg lp-msg-${gps.kind}`} role={gps.kind === "error" ? "alert" : "status"}>
          {gps.text}
        </p>
      )}

      <p className="lp-coords">
        {value ? `Pin set (${value.lat.toFixed(5)}, ${value.lng.toFixed(5)})` : "No pin yet. Tap the map or use GPS."}
        {value && (
          <button type="button" className="lp-clear" onClick={clearPin}>
            Remove pin
          </button>
        )}
      </p>
    </div>
  );
}