import { Icon, type IconName } from "./icons";
import siloBot from "../assets/silo-bot-icon.png"; // the original umbrella + bot art, with a transparent background

interface Props {
  onOpenEmergency?: () => void;
  onOpenIncident: () => void;
  onOpenBot?: () => void; // opens the Ask Silo chat panel
  onAddCenter: () => void;
}

type Tone = "emergency" | "report" | "add";

function ActionButton({
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
    <button type="button" className={`action-btn action-btn-${tone}`} aria-label={ariaLabel} onClick={onClick}>
      <Icon name={icon} size={24} />
      <span className="action-btn-label">{label}</span>
    </button>
  );
}

export function ActionRail({ onOpenEmergency, onOpenIncident, onOpenBot, onAddCenter }: Props) {
  return (
    <nav className="action-row" aria-label="Quick actions">
      <ActionButton tone="emergency" icon="phone" label="Emergency" ariaLabel="Emergency calls" onClick={onOpenEmergency} />
      <ActionButton tone="report" icon="megaphone" label="Report" ariaLabel="Submit incident report" onClick={onOpenIncident} />
      <ActionButton tone="add" icon="plus" label="Add evac" ariaLabel="Add an evacuation center" onClick={onAddCenter} />

      <button
        type="button"
        className="action-btn action-btn-ask"
        aria-label="Ask Silo, the SILONG chatbot"
        onClick={onOpenBot}
      >
        <img className="action-bot-img" src={siloBot} alt="" />
        <span className="action-btn-label">Ask Silo</span>
      </button>
    </nav>
  );
}