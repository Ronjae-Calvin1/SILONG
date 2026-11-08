import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Icon, type IconName } from "./icons";
import { WeatherTab, type WeatherStatus } from "./weatherTab";
import { WarningsTab, type WarningsStatus } from "./WarningsTab";
import { UpdatesTab, type UpdatesStatus } from "./UpdatesTab";

type Props = {
  onHeightChange: (px: number) => void;
  // Goes up by one each time the Alerts button (or the bell) is tapped (0 = never tapped).
  openRequest: number;
};

type Tab = "weather" | "warnings" | "updates";
type Snap = "collapsed" | "half" | "full";

const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: "weather", label: "Weather", icon: "cloud" },
  { id: "warnings", label: "Warnings", icon: "warning" },
  { id: "updates", label: "Updates", icon: "globe" },
];

const COLLAPSED_H = 0; // 0 = fully hidden below the screen
const HALF_RATIO = 0.55;
const FULL_RATIO = 0.78;
// change this to "loading", "error" or "ready", save, and look at the Weather tab.
const WEATHER_STATUS: WeatherStatus = "unavailable";
const WARNINGS_STATUS: WarningsStatus = "unavailable";
const UPDATES_STATUS: UpdatesStatus = "ready";

// TEMPORARY, FOR A SCREENSHOT ONLY. DELETE BEFORE SUBMITTING.
const UPDATE_SAMPLE = [
  {
    id: "s1",
    organization: "Sample News",
    publishedAt: new Date(Date.now() - 3600000),
    summary: "SAMPLE ONLY: this text shows the card layout.",
    sourceUrl: "https://example.com",
    isOfficial: false,
  },
  {
    id: "s2",
    organization: "Sample Agency",
    publishedAt: new Date(Date.now() - 7200000),
    summary: "SAMPLE ONLY: official sources are sorted first.",
    sourceUrl: "https://example.com",
    isOfficial: true,
  },
];

function TabContent({ tab }: { tab: Tab }) {
  if (tab === "weather") {
    return (
      <WeatherTab
        status={WEATHER_STATUS}
        errorMessage={null} 
        lastUpdated={null}
        onRefresh={() => undefined}
      />
    );
  }
   if (tab === "warnings") {
    return (
      <WarningsTab
        status={WARNINGS_STATUS}
        errorMessage={null} 
        lastChecked={null}
        onRetry={() => undefined}
      />
    );
  }
   return (
    <UpdatesTab
      status={UPDATES_STATUS}
      errorMessage={null} updates={UPDATE_SAMPLE}
      onRetry={() => undefined}
    />
  );

}

export function AlertsSheet({ onHeightChange, openRequest }: Props) {
  const [tab, setTab] = useState<Tab>("weather");
  const [snap, setSnap] = useState<Snap>("collapsed");
  const [dragHeight, setDragHeight] = useState<number | null>(null);
  const [viewportH, setViewportH] = useState(window.innerHeight);
  const drag = useRef({ startY: 0, startHeight: 0, moved: false, latest: 0 });

  useEffect(() => {
    function onResize() {
      setViewportH(window.innerHeight);
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

    // The Alerts button / bell was tapped: show the Alerts tab and make sure the
  // sheet is open. If it is already open, only the tab changes.
  useEffect(() => {
    if (openRequest === 0) return;
    setTab("weather");
    setSnap((s) => (s === "collapsed" ? "half" : s));
  }, [openRequest]);

  const fullH = Math.max(COLLAPSED_H, Math.round(viewportH * FULL_RATIO));
  const halfH = Math.max(COLLAPSED_H, Math.round(viewportH * HALF_RATIO));
  const snapHeights: Record<Snap, number> = {
    collapsed: COLLAPSED_H,
    half: halfH,
    full: fullH,
  };

  const dragging = dragHeight !== null;
  const height = dragHeight ?? snapHeights[snap];

  useEffect(() => {
    onHeightChange(height);
  }, [height, onHeightChange]);

  function onPointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { startY: e.clientY, startHeight: height, moved: false, latest: height };
    setDragHeight(height);
  }

  function onPointerMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    const delta = drag.current.startY - e.clientY;
    if (Math.abs(delta) > 5) drag.current.moved = true;
    const next = Math.max(COLLAPSED_H, Math.min(fullH, drag.current.startHeight + delta));
    drag.current.latest = next;
    setDragHeight(next);
  }

  function onPointerUp() {
    if (!dragging) return;
    const finalH = drag.current.latest;
    setDragHeight(null);

    if (!drag.current.moved) {
      setSnap(snap === "collapsed" ? "half" : "collapsed");
      return;
    }
    const names = Object.keys(snapHeights) as Snap[];
    const nearest = names.reduce((a, b) =>
      Math.abs(snapHeights[b] - finalH) < Math.abs(snapHeights[a] - finalH) ? b : a
    );
    setSnap(nearest);
  }

  function chooseTab(t: Tab) {
    setTab(t);
    if (snap === "collapsed") setSnap("half");
  }
  const classes = ["sheet"];
  if (dragging) classes.push("sheet-dragging");
  if (snap === "collapsed" && !dragging) classes.push("sheet-closed");

  return (
    <section
      className={classes.join(" ")}
      aria-label="Early Warning Alerts"
      style={{
        height: `${fullH}px`,
        transform: `translateY(${fullH - height}px)`,
      }}
    >
      {/* Drag area: handle + title */}
      <div
        className="sheet-drag"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div className="sheet-handle" />
        <h2 className="sheet-title">Early Warning Alerts</h2>
      </div>

      {/* X sits outside the drag area so taps on it still work.
          It shrinks the sheet to the small bar; it never removes it. */}
      <button
        className="sheet-close"
        aria-label="Close alerts"
        onClick={() => setSnap("collapsed")}
      >
        <Icon name="close" size={20} />
      </button>

      <div className="sheet-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-label={t.label}
            aria-selected={tab === t.id}
            className={`sheet-tab${tab === t.id ? " sheet-tab-active" : ""}`}
            onClick={() => chooseTab(t.id)}
          >
            <Icon name={t.icon} size={20} />
            <span className="sheet-tab-label">{t.label}</span>
          </button>
        ))}
      </div>

      <div className="sheet-body" role="tabpanel">
        <TabContent tab={tab} />
      </div>
    </section>
  );
}