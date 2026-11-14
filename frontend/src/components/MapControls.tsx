import { Icon } from "./icons";

interface Props {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onLocate: () => void;
  locating: boolean;
}

// Zoom in, zoom out and "show my location". Shown on desktop only (phones use pinch to zoom).
export function MapControls({ onZoomIn, onZoomOut, onLocate, locating }: Props) {
  return (
    <div className="map-zoom" role="group" aria-label="Map controls">
      <button type="button" className="map-zoom-btn" onClick={onZoomIn} aria-label="Zoom in">
        <Icon name="plus" size={26} />
      </button>
      <button type="button" className="map-zoom-btn" onClick={onZoomOut} aria-label="Zoom out">
        <Icon name="minus" size={26} />
      </button>
      <button
        type="button"
        className="map-zoom-btn map-zoom-btn-locate"
        onClick={onLocate}
        aria-label="Show my location"
        aria-busy={locating}
      >
        <Icon name="locate" size={26} />
      </button>
    </div>
  );
}