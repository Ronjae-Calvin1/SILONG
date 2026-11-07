import { APP_NAME } from "./appName";
import { Icon } from "./icons";

interface Props {
  menuOpen?: boolean;
  onMenuClick?: () => void; // the menu button opens the "Removed centers" list for now
}

export function TopBar({ menuOpen = false, onMenuClick }: Props) {
  return (
    <header className="topbar">
      <button className="topbar-btn" aria-label="Menu" aria-expanded={menuOpen} onClick={onMenuClick}>
        <Icon name="menu" />
      </button>

      <div className="topbar-logo">{APP_NAME}</div>

      <div className="topbar-right">
        <button className="topbar-btn" aria-label="Search location">
          <Icon name="pin" />
        </button>
        <button className="topbar-btn" aria-label="Profile">
          <Icon name="user" />
        </button>
      </div>
    </header>
  );
}