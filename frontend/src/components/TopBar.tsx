import logoWhite from "../assets/silong-logo-white.png";
import { Icon } from "./icons";

interface Props {
  menuOpen?: boolean;
  onMenuClick?: () => void; // opens or closes the menu (the HamburgerMenu window)
}

// The top bar only has the menu button and the logo. Every link lives in the menu.
export function TopBar({ menuOpen = false, onMenuClick }: Props) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button
          type="button"
          className="topbar-btn"
          aria-label="Menu"
          aria-haspopup="dialog"
          aria-expanded={menuOpen}
          onClick={onMenuClick}
        >
          <Icon name="menu" size={24} />
        </button>

        <img className="topbar-logo" src={logoWhite} alt="SILONG" width={800} height={228} />
      </div>
    </header>
  );
}