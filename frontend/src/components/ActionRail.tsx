import { useState } from "react";
import { Icon, type IconName } from "./icons";
import siloBot from "../assets/silo-bot.png";

interface Props {
  onOpenEmergency?: () => void; // optional on purpose: the Emergency Hotlines panel is not built yet
  onOpenIncident: () => void;
  onOpenAlerts: () => void;
  onOpenBot?: () => void; // optional on purpose: the chatbot panel is not built yet
  onAddCenter: () => void;
}

type Tone = "emergency" | "report" | "alerts" | "add";

// One square button: icon on top, small label underneath.
function RailButton({
  tone,
  icon,
  label,
  ariaLabel,
  onClick,
}: {
  tone: Tone;
  icon: IconName;
  label: string;
  ariaLabel: string;
  onClick?: () => void;
}) {
  return (
    <button type="button" className={`rail-btn rail-btn-${tone}`} aria-label={ariaLabel} onClick={onClick}>
      <Icon name={icon} size="var(--icon-lg)" />
      <span className="rail-btn-label">{label}</span>
    </button>
  );
}

export function ActionRail({ onOpenEmergency, onOpenIncident, onOpenAlerts, onOpenBot, onAddCenter }: Props) {
  // The chevron at the top folds the rail away so it never blocks the map on small screens.
  const [collapsed, setCollapsed] = useState(false);

  return (
    <nav className="rail" data-collapsed={collapsed} aria-label="Quick actions">
      <button
        type="button"
        className="rail-toggle"
        aria-expanded={!collapsed}
        aria-label={collapsed ? "Show quick actions" : "Hide quick actions"}
        onClick={() => setCollapsed((c) => !c)}
      >
        <Icon name="chevronUp" size="var(--icon-xl)" />
      </button>

      {!collapsed && (
        <>
          <RailButton
            tone="emergency"
            icon="phone"
            label={"Emer\u00ADgency"}
            ariaLabel="Emergency calls"
            onClick={onOpenEmergency}
          />
          <RailButton
            tone="report"
            icon="megaphone"
            label="Report"
            ariaLabel="Submit incident report"
            onClick={onOpenIncident}
          />
          <RailButton tone="alerts" icon="warning" label="Alerts" ariaLabel="Alerts" onClick={onOpenAlerts} />
          
          <RailButton
            tone="add"
            icon="plus"
            label="Add evac"
            ariaLabel="Add center: add an evacuation center"
            onClick={onAddCenter}
          />

          {/* Round bot button, last in the rail like the design */}
          <button type="button" className="rail-bot" aria-label="SILONG Bot assistant" onClick={onOpenBot}>
            <img className="rail-bot-img" src={siloBot} alt="" />
          </button>
        </>
      )}
    </nav>
  );
}