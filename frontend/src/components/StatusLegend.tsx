// Small key that explains the pin colors. Display only: nothing here is a button.
// Every color is paired with a word, so the meaning never depends on color alone.
// It is drawn twice on purpose (bottom of the map on phones, inside the side card on
// desktop); MapPage.css shows only the one that fits the screen size.

const ITEMS = [
  { status: "open", label: "Open" },
  { status: "almost-full", label: "Almost full" },
  { status: "full", label: "Full" },
  { status: "closed", label: "Closed" },
] as const;

interface Props {
  variant: "map" | "side";
}

export function StatusLegend({ variant }: Props) {
  return (
    <ul className={`legend legend-${variant}`} aria-label="What the pin colors mean">
      {ITEMS.map((item) => (
        <li key={item.status} className="legend-item">
          <span className="legend-dot" data-status={item.status} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
  );
}