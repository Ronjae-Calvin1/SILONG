import { Icon } from "./icons";

interface Props {
  onOpen: () => void; // opens the Early Warning Alerts sheet
  // The strip only says what is true today: weather is not live yet, so it does not show a
  // temperature. When real weather is connected, pass the real values in here.
  headline?: string;
  detail?: string;
}

export function WeatherStrip({
  onOpen,
  headline = "Weather and warnings",
  detail = "Tap to open alerts · Batangas City",
}: Props) {
  return (
    <button
      type="button"
      className="weather-strip"
      aria-label={`${headline}. ${detail}. Opens the early warning alerts.`}
      onClick={onOpen}
    >
      <span className="weather-strip-icon" aria-hidden="true">
        <Icon name="cloud" size={28} />
      </span>
      <span className="weather-strip-text">
        <span className="weather-strip-title">{headline}</span>
        <span className="weather-strip-sub">{detail}</span>
      </span>
      <span className="weather-strip-chevron" aria-hidden="true">
        <Icon name="chevronUp" size={24} />
      </span>
    </button>
  );
}