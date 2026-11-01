import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Icon, type IconName } from "./icons";

type Props = {
  onHeightChange: (px: number) => void; 
};

type Tab = "warning" | "alerts" | "internet";
type Snap = "collapsed" | "half" | "full";

const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: "warning", label: "Warning", icon: "warning" },
  { id: "alerts", label: "Alerts", icon: "bell" },
  { id: "internet", label: "Internet updates", icon: "globe" },
];

const COLLAPSED_H = 112; 
const HALF_RATIO = 0.4; 
const FULL_RATIO = 0.6;

function Cards({ count, text }: { count: number; text: string }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div className="sheet-card" key={i}>
          {text}
        </div>
      ))}
    </>
  );
}

function TabContent({ tab }: { tab: Tab }) {
  if (tab === "warning") {
    return (
      <>
        <h3 className="sheet-heading sheet-heading-red">Latest tropical cyclones</h3>
        <Cards count={1} text="Placeholder: cyclone info will appear here." />
        <h3 className="sheet-heading">Weather forecast</h3>
        <Cards count={1} text="Placeholder: forecast will appear here." />
      </>
    );
  }
  if (tab === "alerts") {
    return (
      <>
        <h3 className="sheet-heading sheet-heading-red">Alerts / Warnings</h3>
        <Cards count={4} text="Placeholder: alert will appear here." />
      </>
    );
  }
  return (
    <>
      <h3 className="sheet-heading">Internet updates</h3>
      <Cards count={3} text="Placeholder: update will appear here." />
    </>
  );
}

export function AlertsSheet({ onHeightChange }: Props) {
  const [tab, setTab] = useState<Tab>("warning");
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
        aria-label="Collapse alerts"
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
            <Icon name={t.icon} size={22} />
          </button>
        ))}
      </div>

      <div className="sheet-body" role="tabpanel">
        <TabContent tab={tab} />
      </div>
    </section>
  );
}