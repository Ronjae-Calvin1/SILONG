import type { ReactNode } from "react";
import { Icon } from "./icons";
import "./AlertsTabs.css";

// The four situations the Weather tab can be in.
export type WeatherStatus = "loading" | "error" | "unavailable" | "ready";

type Props = {
  status: WeatherStatus;
  errorMessage: string | null; // plain-language message shown in the "error" state
  location?: string;
  lastUpdated: Date | null; // null = never loaded
  cyclone?:string | null; // name of the cyclone, if any
  onRefresh: () => void;
  children?: ReactNode; // the weather cards go here (added in a later step)
};

export function WeatherTab({
  status,
  errorMessage,
  location = "Batangas City",
  lastUpdated,
  cyclone = null,
  onRefresh,
  children,
}: Props) {
  const updatedText = lastUpdated
    ? `Last updated: ${lastUpdated.toLocaleTimeString("en-PH", { hour: "numeric", minute: "2-digit" })}`
    : "Last updated: not yet";

  // Refreshing only makes sense when there is something to refresh.
  const canRefresh = status === "ready" || status === "error";

  return (
    <div className="weather-tab">
      <div className="weather-location">
        <span className="weather-location-name">
          <Icon name="pin" size={18} />
          {location}
        </span>
        <button className="weather-refresh" onClick={onRefresh} disabled={!canRefresh}>
          <Icon name="refresh" size={16} />
          Refresh
        </button>
      </div>

      <p className="weather-updated">{updatedText}</p>

      {status !== "loading" && (
        <p className="weather-cyclone">
          <strong>Tropical cyclone:</strong> {cyclone ?? "Not available right now. Check PAGASA."}
        </p>
      )}

      {status === "loading" && (
        <div className="state-box" role="status">
          <strong>Loading weather…</strong>
        </div>
      )}

      {status === "error" && (
        <div className="state-box state-box-error" role="alert">
          <strong>Couldn't load the weather</strong>
          <p>{errorMessage ?? "Something went wrong. Please try again."}</p>
        </div>
      )}

      {status === "unavailable" && (
        <div className="state-box">
          <strong>Weather isn't connected yet</strong>
          <p>
            SILONG can't show live weather right now. For the latest conditions, check PAGASA.
          </p>
          <a
            className="state-link"
            href="https://www.pagasa.dost.gov.ph/"
            target="_blank"
            rel="noopener noreferrer"
          >
            Open PAGASA ↗
          </a>
        </div>
      )}

      {status === "ready" && children}

      <p className="alerts-disclaimer">
        <strong>Official advisories come first.</strong> This is a weather forecast for a point on the
        map. It is not PAGASA's official storm track.
      </p>
    </div>
  );
}