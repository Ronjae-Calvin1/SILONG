import { APP_NAME } from "./appName";
import { Icon } from "./icons";

export function TopBar() {
  return (
    <header className="topbar">
      <button className="topbar-btn" aria-label="Menu">
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