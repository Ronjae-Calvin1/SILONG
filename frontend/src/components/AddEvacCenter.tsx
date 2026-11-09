import { useEffect, useRef, useState, type RefObject } from "react";
import maplibregl from "maplibre-gl";
import type { Facility } from "../types";
import { EMPTY_DRAFT, type CenterDraft } from "./evacCenterDraft";
import { EvacCenterForm } from "./EvacCenterForm";
import "./EvacManager.css";

// idle      -> only the "Add evacuation center" button is showing
// placing   -> banner says "Tap the map", no pin yet
// placed    -> pin is on the map and can be dragged (or the map tapped again to move it)
// form      -> details form is open on top of the map
type Phase = "idle" | "placing" | "placed" | "form";

interface Point {
  lng: number;
  lat: number;
}

interface Props {
  mapRef: RefObject<maplibregl.Map | null>;
  // Called when adding starts or ends, so the page can close the details panel
  // and ignore taps on the other pins meanwhile.
  onActiveChange: (active: boolean) => void;
  // The server saved the new center; the page adds its pin.
  onAdded: (facility: Facility) => void;
  startRequest:number;
}

// Same pin shape as the facility pins in MapPage, so the tip sits exactly on the coordinates.
const PIN_OFFSET: [number, number] = [0, -22];

function makeMarkerElement(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "pin evac-marker";
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", "New evacuation center location. Drag to move it.");
  const body = document.createElement("div");
  body.className = "pin-body";
  const letter = document.createElement("span");
  letter.className = "pin-letter";
  letter.textContent = "+";
  body.appendChild(letter);
  el.appendChild(body);
  return el;
}

export function AddEvacCenter({ mapRef, onActiveChange, onAdded, startRequest }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [point, setPoint] = useState<Point | null>(null);
  const [draft, setDraft] = useState<CenterDraft>(EMPTY_DRAFT);
  const markerRef = useRef<maplibregl.Marker | null>(null);

  function go(next: Phase) {
    setPhase(next);
    onActiveChange(next !== "idle");
  }

  // The one place that puts or moves the pin. Tapping the map calls it today;
  // a future "Use my GPS" button only needs to call placePin({ lng, lat }) with
  // the device position (and, if wanted, map.easeTo that point).
  function placePin(p: Point) {
    const map = mapRef.current;
    if (!map) return;
    let marker = markerRef.current;
    if (marker) {
      marker.setLngLat([p.lng, p.lat]);
    } else {
      // draggable: MapLibre stops the map from panning while a drag that started on the pin is going on.
      marker = new maplibregl.Marker({
        element: makeMarkerElement(),
        anchor: "center",
        offset: PIN_OFFSET,
        draggable: true,
      })
        .setLngLat([p.lng, p.lat])
        .addTo(map);
      const created = marker;
      created.on("dragend", () => {
        const at = created.getLngLat();
        setPoint({ lng: at.lng, lat: at.lat });
      });
      markerRef.current = marker;
    }
    setPoint(p);
    setPhase((cur) => (cur === "placing" ? "placed" : cur));
  }

  function removeMarker() {
    markerRef.current?.remove();
    markerRef.current = null;
  }

  function finish() {
    removeMarker();
    setPoint(null);
    setDraft(EMPTY_DRAFT);
    go("idle");
  }

  // While placing, a tap on the map puts the pin there. A tap that is really a pan does not count (MapLibre decides).
  const picking = phase === "placing" || phase === "placed";
  useEffect(() => {
    
    const map = mapRef.current;
    if (!map || !picking) return;
    const onClick = (e: maplibregl.MapMouseEvent) => {
      // A tap on the pin itself must not make it jump to the tapped spot.
      if (markerRef.current?.getElement().contains(e.originalEvent.target as Node)) return;
      placePin({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    };
    map.on("click", onClick);
    map.getCanvas().style.cursor = "crosshair";
    return () => {
      map.off("click", onClick);
      map.getCanvas().style.cursor = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picking]);

  // Leaving the page removes the map itself; this just makes sure the pin is gone too.
  useEffect(() => removeMarker, []);
  // The rail's "Add center" button asks us to start. We only start from the
  // idle state, so a second tap while placing does nothing.
  useEffect(() => {
    if (startRequest > 0 && phase === "idle") go("placing");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startRequest]);
  

  return (
    <>

      {picking && (
        <div className="evac-banner" role="status">
          <p className="evac-banner-text">
            {phase === "placing" ? "Tap the map to place the center" : "Drag the pin to adjust it, then tap Continue"}
          </p>
          <div className="evac-banner-actions">
            <button className="evac-banner-btn evac-banner-cancel" onClick={finish}>
              Cancel
            </button>
            {phase === "placed" && (
              <button className="evac-banner-btn evac-banner-go" onClick={() => go("form")}>
                Continue
              </button>
            )}
          </div>
        </div>
      )}

      {phase === "form" && point && (
        <EvacCenterForm
          point={point}
          draft={draft}
          onDraftChange={(patch) => setDraft((cur) => ({ ...cur, ...patch }))}
          onBackToMap={() => go("placed")}
          onSaved={(facility) => {
            onAdded(facility);
            finish();
          }}
        />
      )}
    </>
  );
}
