import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { AdminReport, Place } from "../api/types";
import { DEFAULT_CENTER, MAP_STYLE } from "./mapStyle";

export interface Layers {
  reports: boolean; // open "Needs help" reports
  hazards: boolean; // open hazards
  resolved: boolean; // closed reports in the list (they are there when the Resolved filter is on)
  places: boolean;
}

interface Props {
  reports: AdminReport[];
  places: Place[];
  layers: Layers;
  selectedId: number | null;
  onSelect: (id: number) => void;
  compact?: boolean; // the small map on the phone's report detail
}

function pinClass(r: AdminReport): string {
  if (r.status === "resolved" || r.status === "false") return "pin pin-closed";
  return r.kind === "help" ? "pin pin-help" : "pin pin-hazard";
}

function showReport(r: AdminReport, l: Layers): boolean {
  if (r.status === "resolved" || r.status === "false") return l.resolved;
  return r.kind === "help" ? l.reports : l.hazards;
}

export default function LiveMap({ reports, places, layers, selectedId, onSelect, compact = false }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markers = useRef(new Map<string, { marker: maplibregl.Marker; dot: HTMLElement }>());
  const onSelectRef = useRef(onSelect);
  const fitted = useRef(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    if (!box.current) return;
    const map = new maplibregl.Map({
      container: box.current,
      style: MAP_STYLE,
      center: DEFAULT_CENTER,
      zoom: compact ? 15 : 13,
      interactive: !compact,
      attributionControl: compact ? false : { compact: true },
    });
    if (!compact) map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    setReady(true);
    const pins = markers.current;
    return () => {
      pins.forEach((m) => m.marker.remove());
      pins.clear();
      map.remove();
      mapRef.current = null;
    };
  }, [compact]);

  // Keep one marker per report and per place. Selecting a card and a pin select each other.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const wanted = new Map<string, { lng: number; lat: number; cls: string; label: string; id?: number }>();
    for (const r of reports) {
      if (showReport(r, layers)) {
        wanted.set(`r${r.id}`, {
          lng: r.longitude,
          lat: r.latitude,
          cls: pinClass(r) + (r.id === selectedId ? " pin-selected" : ""),
          label: r.category ?? r.kind,
          id: r.id,
        });
      }
    }
    if (layers.places) {
      for (const p of places) wanted.set(`p${p.id}`, { lng: p.longitude, lat: p.latitude, cls: "pin pin-place", label: p.name });
    }
    const pins = markers.current;
    for (const [key, m] of pins) {
      if (!wanted.has(key)) {
        m.marker.remove();
        pins.delete(key);
      }
    }
    for (const [key, w] of wanted) {
      const existing = pins.get(key);
      if (existing) {
        existing.dot.className = w.cls;
        existing.marker.setLngLat([w.lng, w.lat]);
        continue;
      }
      const el = document.createElement("div");
      const dot = document.createElement("span");
      dot.className = w.cls;
      dot.textContent = w.id === undefined ? "" : "!";
      dot.title = w.label;
      el.appendChild(dot);
      if (w.id !== undefined) {
        const id = w.id;
        el.style.cursor = "pointer";
        el.addEventListener("click", () => onSelectRef.current(id));
      }
      const marker = new maplibregl.Marker({ element: el }).setLngLat([w.lng, w.lat]).addTo(map);
      pins.set(key, { marker, dot });
    }

    // First time there are pins, show them all.
    if (!fitted.current && !compact) {
      const pts = reports.filter((r) => showReport(r, layers));
      if (pts.length > 0) {
        fitted.current = true;
        const b = new maplibregl.LngLatBounds();
        pts.forEach((r) => b.extend([r.longitude, r.latitude]));
        map.fitBounds(b, { padding: 70, maxZoom: 16, duration: 0 });
      }
    }
  }, [ready, reports, places, layers, selectedId, compact]);

  // Move to the selected report (or, on the small map, keep it centred).
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || selectedId === null) return;
    const r = reports.find((x) => x.id === selectedId);
    if (r) map.easeTo({ center: [r.longitude, r.latitude], duration: compact ? 0 : 400 });
  }, [ready, selectedId, reports, compact]);

  return <div ref={box} className={compact ? "map map-compact" : "map"} />;
}
