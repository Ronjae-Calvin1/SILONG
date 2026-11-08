import logoWhite from "../assets/silong-logo-white.png";
import { Icon } from "./icons";

interface Props {
  menuOpen?: boolean;
  onMenuClick?: () => void; // the menu button opens the "Removed centers" list for now
  onBellClick?: () => void; // optional on purpose: notifications are not built yet
}

export function TopBar({ menuOpen = false, onMenuClick, onBellClick }: Props) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="topbar-btn" aria-label="Menu" aria-expanded={menuOpen} onClick={onMenuClick}>
          <Icon name="menu" size={23} />
        </button>

        <img className="topbar-logo" src={logoWhite} alt="SILONG" width={800} height={228} />
      </div>

      <button className="topbar-btn" aria-label="Notifications" onClick={onBellClick}>
        <Icon name="bell" size={23} />
      </button>
    </header>
  );
}