import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import logoWhite from "../assets/silong-logo-white.png";
import { Icon, type IconName } from "./icons";
import type { HiddenCenter } from "./hiddenCenters";
import { loadMyPlaces, loadMyReports } from "./myActivity";
import { AboutPage, FaqPage, MyActivityPage, MyPlacesPage, MyReportsPage, type MenuPage } from "./MenuPages";
import "./HamburgerMenu.css";

interface Props {
  hidden: HiddenCenter[]; // centers hidden on this phone (kept by the map page, which also hides the pins)
  onUnhide: (id: number) => void;
  page: MenuPage | null; // the page being shown (null = the menu list). Kept by the map page so the desktop top bar can open pages too.
  onPage: (page: MenuPage | null) => void;
  onClose: () => void; // closes the whole menu and shows the map
}

// Desktop (1024px and wider): a page was opened from the top bar, so "back" simply closes it.
const isDesktop = () => window.matchMedia("(min-width: 1024px)").matches;

// Is an element really on screen and usable? (hidden with display:none, or inside an inert part, = no)
const isUsable = (el: HTMLElement) => el.offsetParent !== null && !el.closest("[inert]");

// The menu row that opens a page or closes the menu.
function Row({
  icon,
  label,
  count,
  active,
  onClick,
}: {
  icon: IconName;
  label: string;
  count?: number;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button type="button" className="hm-row" aria-current={active ? "page" : undefined} onClick={onClick}>
        <Icon name={icon} size={22} />
        <span className="hm-row-label">{label}</span>
        {count !== undefined && count > 0 && (
          <span className="hm-count" aria-label={`${count}`}>
            {count}
          </span>
        )}
      </button>
    </li>
  );
}

// The public menu (slides in from the left). It is mounted only while it is open, so the counts
// for "My Suggested Places" and "My Reports" are read fresh from this phone every time it opens.
export function HamburgerMenu({ hidden, onUnhide, page, onPage, onClose }: Props) {
  const navigate = useNavigate();
  const [hiddenOpen, setHiddenOpen] = useState(true);
  const [reports] = useState(loadMyReports);
  const [places] = useState(loadMyPlaces);
  const rootRef = useRef<HTMLDivElement>(null);

  // On phones a page covers the whole screen, so the menu list underneath must not be reachable
  // (keyboard or screen reader) while it is covered. We keep it mounted instead of hiding it, so
  // its slide-in animation does not play again when you come back.
  const [phone, setPhone] = useState(() => !isDesktop());
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = () => setPhone(!mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // Keyboard: focus goes into the menu when it opens (or when a page opens) and back to the
  // button that opened it when the menu closes. Escape goes back one step. Tab stays inside.
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    return () => before?.focus?.();
  }, []);

  useEffect(() => {
    const items = Array.from(rootRef.current?.querySelectorAll<HTMLElement>("[data-autofocus]") ?? []);
    // preventScroll: the page is still sliding in, and without it the browser may scroll
    // the screen sideways to reach the button (that was the "bouncing").
    items.find(isUsable)?.focus({ preventScroll: true });
  }, [page]);

  // Desktop: the window has the menu on the left and a page on the right, so one page is always selected.
  useEffect(() => {
    if (page === null && isDesktop()) onPage("about");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Back from a page: phones go back to the menu list, desktop closes the page.
  function goBack() {
    if (isDesktop()) onClose();
    else onPage(null);
  }

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (page && !window.matchMedia("(min-width: 1024px)").matches) onPage(null);
      else onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [page, onPage, onClose]);

  function trapTab(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Tab" || !rootRef.current) return;
    const items = Array.from(
      rootRef.current.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], [tabindex='0']"),
    ).filter(isUsable);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  let pageBody: ReactNode = null;
  if (page === "activity") {
    pageBody = <MyActivityPage reports={reports} places={places} onBack={goBack} />;
  } else if (page === "reports") {
    pageBody = <MyReportsPage reports={reports} onBack={goBack} />;
  } else if (page === "places") {
    pageBody = <MyPlacesPage places={places} onBack={goBack} />;
  } else if (page === "about") {
    pageBody = <AboutPage onBack={goBack} />;
  } else if (page === "faq") {
    pageBody = <FaqPage onBack={goBack} />;
  }

  const drawer = (
    <nav className="hm-drawer" aria-label="Menu" inert={phone && page !== null}>
      <header className="hm-header">
        <div className="hm-header-top">
          <img className="hm-logo" src={logoWhite} alt="SILONG" width={800} height={228} />
          <button type="button" className="hm-close" aria-label="Close menu" onClick={onClose} data-autofocus>
            <Icon name="close" size={24} />
          </button>
        </div>
        <p className="hm-tagline">Safety, Information, Location, and Operations Network Guide</p>
      </header>

      <div className="hm-scroll">
        <ul className="hm-list">
          <Row icon="pin" label="Map" onClick={onClose} />
          <Row icon="list" label="About SILONG" active={page === "about"} onClick={() => onPage("about")} />
          <Row
            icon="warning"
            label="My Suggested Places"
            count={places.length}
            active={page === "places"}
            onClick={() => onPage("places")}
          />
          <Row
            icon="megaphone"
            label="My Reports"
            count={reports.length}
            active={page === "reports"}
            onClick={() => onPage("reports")}
          />
          <Row icon="search" label="FAQs" active={page === "faq"} onClick={() => onPage("faq")} />
        </ul>

        <section className="hm-hidden">
          <button
            type="button"
            className="hm-row hm-row-toggle"
            aria-expanded={hiddenOpen}
            aria-controls="hm-hidden-body"
            onClick={() => setHiddenOpen((o) => !o)}
          >
            <Icon name="eyeOff" size={22} />
            <span className="hm-row-label">Hidden on this phone</span>
            <Icon name={hiddenOpen ? "chevronUp" : "chevronDown"} size={20} />
          </button>

          {hiddenOpen && (
            <div id="hm-hidden-body" className="hm-hidden-body">
              {hidden.length === 0 ? (
                <p className="hm-empty">
                  No hidden centers. To hide one, open an evacuation center on the map and tap Hide on this phone.
                </p>
              ) : (
                <ul className="hm-cards">
                  {hidden.map((c) => (
                    <li className="hm-card" key={c.id}>
                      <div className="hm-card-info">
                        <span className="hm-card-name">{c.name}</span>
                        <span className="hm-card-kind">{c.kind}</span>
                      </div>
                      <button
                        type="button"
                        className="hm-unhide"
                        aria-label={`Unhide ${c.name}`}
                        onClick={() => onUnhide(c.id)}
                      >
                        Unhide
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="hm-note">Clearing your browser data shows hidden centers again.</p>
            </div>
          )}
        </section>
      </div>

      <footer className="hm-footer">
        <ul className="hm-list">
          <Row icon="lock" label="Admin sign in" onClick={() => navigate("/admin")} />
        </ul>
      </footer>
    </nav>
  );

  return (
    <div
      className="hm-root"
      ref={rootRef}
      data-page={page ? "open" : "none"}
      onKeyDown={trapTab}
      role="dialog"
      aria-modal="true"
      aria-label="SILONG menu"
    >
      {/* Phones: the menu list OR the open page fills the screen. Desktop: one floating window, menu on the left, page on the right. */}
      <div className="hm-modal">
        {drawer}
        <div className="hm-content">{pageBody}</div>
        <button type="button" className="hm-modal-close" aria-label="Close menu" onClick={onClose} data-autofocus>
          <Icon name="close" size={24} />
        </button>
      </div>
      {/* Tapping the dimmed map closes the menu. Keyboard users have the X button and Escape. */}
      <button type="button" className="hm-backdrop" tabIndex={-1} aria-hidden="true" onClick={onClose} />
    </div>
  );
}