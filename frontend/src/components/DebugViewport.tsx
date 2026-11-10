import { useEffect, useState } from "react";

// Dev-only readout of the screen numbers that matter for sizing. Shown while running
// "npm run dev", or in any build when the address has ?debug=1. Add ?debug=0 to hide it in dev.
// It ignores taps, so it never blocks the page.
function enabled(): boolean {
  const flag = new URLSearchParams(window.location.search).get("debug");
  if (flag === "1") return true;
  if (flag === "0") return false;
  return import.meta.env.DEV;
}

function read() {
  const vv = window.visualViewport;
  // --u is a clamp() string, so measure a probe element to get its real px value.
  const probe = document.createElement("div");
  probe.style.cssText = "position:absolute;visibility:hidden;width:var(--u);height:0";
  document.body.appendChild(probe);
  const u = probe.getBoundingClientRect().width;
  probe.remove();
  return {
    inner: `${window.innerWidth} x ${window.innerHeight}`,
    dpr: window.devicePixelRatio,
    screen: `${window.screen.width} x ${window.screen.height}`,
    visual: vv ? `${Math.round(vv.width * 10) / 10} x ${Math.round(vv.height * 10) / 10}` : "n/a",
    u: Math.round(u * 1000) / 1000,
  };
}

export function DebugViewport() {
  const [on] = useState(enabled);
  const [info, setInfo] = useState(read);

  useEffect(() => {
    if (!on) return;
    const update = () => setInfo(read());
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    return () => {
      window.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("resize", update);
    };
  }, [on]);

  if (!on) return null;
  return (
    <pre
      data-testid="debug-viewport"
      style={{
        position: "fixed",
        left: 4,
        bottom: 4,
        zIndex: 99999,
        margin: 0,
        padding: "4px 6px",
        borderRadius: 4,
        background: "rgba(0,0,0,0.75)",
        color: "#7CFC8A",
        font: "11px/1.35 ui-monospace, Menlo, monospace",
        pointerEvents: "none",
      }}
    >
      {`inner   ${info.inner}\ndpr     ${info.dpr}\nscreen  ${info.screen}\nvisual  ${info.visual}\n--u     ${info.u}px`}
    </pre>
  );
}
