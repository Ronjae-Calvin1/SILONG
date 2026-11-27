import type { StyleSpecification } from "maplibre-gl";

// Same behaviour as the user site: MapTiler when a key is set, plain OpenStreetMap when it is empty.
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;
const MAPTILER_STYLE = (import.meta.env.VITE_MAPTILER_STYLE as string | undefined) || "streets-v2";

const FALLBACK_STYLE: StyleSpecification = {
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

export const MAP_STYLE: string | StyleSpecification = MAPTILER_KEY
  ? `https://api.maptiler.com/maps/${MAPTILER_STYLE}/style.json?key=${MAPTILER_KEY}`
  : FALLBACK_STYLE;

// Batangas City (longitude, latitude)
export const DEFAULT_CENTER: [number, number] = [121.0583, 13.7565];
