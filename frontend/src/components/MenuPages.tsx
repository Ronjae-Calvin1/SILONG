import { useState, type ReactNode } from "react";
import { Icon } from "./icons";
import type { MyPlace, MyReport } from "./myActivity";
import { timeAgo } from "./statusInfo";
import "./HamburgerMenu.css";

// "activity" = phone (one page with two tabs). "reports" and "places" = desktop (one page each).
export type MenuPage = "activity" | "reports" | "places" | "about" | "faq";

// Support contact details are set by the Super admin once staff accounts exist. Until then they come
// from frontend/.env (VITE_SUPPORT_EMAIL, VITE_SUPPORT_PHONE). If they are empty nothing is invented.
const SUPPORT_EMAIL = (import.meta.env.VITE_SUPPORT_EMAIL as string | undefined)?.trim() ?? "";
const SUPPORT_PHONE = (import.meta.env.VITE_SUPPORT_PHONE as string | undefined)?.trim() ?? "";

// Frame shared by every page opened from the menu: blue bar with a back arrow, scrolling body.
function PageShell({ title, onBack, children }: { title: string; onBack: () => void; children: ReactNode }) {
  return (
    <section className="hm-page" aria-label={title}>
      <header className="hm-page-header">
        <button type="button" className="hm-back" aria-label="Back to menu" onClick={onBack} data-autofocus>
          <Icon name="chevronLeft" size={26} />
        </button>
        <h2 className="hm-page-title">{title}</h2>
      </header>
      <div className="hm-page-body">{children}</div>
    </section>
  );
}

// ---------- About SILONG ----------
export function AboutPage({ onBack }: { onBack: () => void }) {
  return (
    <PageShell title="About SILONG" onBack={onBack}>
      <div className="hm-prose">
        <p>
          SILONG (Safety, Information, Location, and Operations Network Guide) helps people in Batangas City during a
          storm or other emergency.
        </p>
        <p>
          It shows where the nearest hospitals, clinics and evacuation centers are, and whether those places are open,
          busy or full. Anyone can use the map and update a place&rsquo;s status. There is no sign-up and no login.
        </p>
        <p>Official advisories from PAGASA, NDRRMC and the city always come first.</p>
        <p className="hm-prose-small">Map data &copy; OpenStreetMap contributors. Base map &copy; MapTiler.</p>
      </div>
    </PageShell>
  );
}

// ---------- FAQs and help (+ Contact support) ----------
const FAQS: { q: string; a: string }[] = [
  {
    q: "How do I know a place has space?",
    a: "Tap its pin. You see the status, how full it is, and when it was last updated.",
  },
  {
    q: "Who updates the status?",
    a: "Anyone. There are no accounts: tap a pin, then Update status. The newest report is the one shown, with the time it was sent.",
  },
  {
    q: "Why does a pin look faded?",
    a: "Its last update is more than 6 hours old, so the status may be outdated. Faded pins have a dashed ring and say “May be outdated” in their details.",
  },
  {
    q: "What does “I need help” do?",
    a: "It is the option in the Report form for when you need help yourself. It is meant for responders only and is never shown on the map. In danger? Call 911 first.",
  },
  {
    q: "Is my location shared?",
    a: "Your location is used on your phone to show where you are and to sort places by distance. When you send a report, the spot you choose (your GPS location or a point on the map) is saved with that report.",
  },
  {
    q: "Can I add or hide a place?",
    a: "Yes, for evacuation centers. Use Add evac to put a center on the map. Use Hide on this phone to hide a center only on your phone: other people still see it, and you can show it again from this menu. Hospitals and clinics cannot be hidden.",
  },
];

export function FaqPage({ onBack }: { onBack: () => void }) {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <PageShell title="FAQs and help" onBack={onBack}>
      <ul className="hm-faq">
        {FAQS.map((item, i) => {
          const isOpen = open === i;
          return (
            <li className="hm-faq-item" key={item.q}>
              <h3 className="hm-faq-heading">
                <button
                  type="button"
                  className="hm-faq-q"
                  aria-expanded={isOpen}
                  aria-controls={`hm-faq-a-${i}`}
                  onClick={() => setOpen(isOpen ? null : i)}
                >
                  <span>{item.q}</span>
                  <Icon name={isOpen ? "chevronUp" : "plus"} size={22} />
                </button>
              </h3>
              {isOpen && (
                <p className="hm-faq-a" id={`hm-faq-a-${i}`}>
                  {item.a}
                </p>
              )}
            </li>
          );
        })}
      </ul>

      <section className="hm-support" aria-labelledby="hm-support-title">
        <h3 className="hm-support-title" id="hm-support-title">
          Contact support
        </h3>
        <p className="hm-support-text">For problems with the app. For emergencies, call 911.</p>

        <div className="hm-support-row">
          <Icon name="mail" size={22} />
          {SUPPORT_EMAIL ? (
            <a className="hm-support-link" href={`mailto:${SUPPORT_EMAIL}`}>
              {SUPPORT_EMAIL}
            </a>
          ) : (
            <span className="hm-support-unset">Email not set yet</span>
          )}
        </div>
        <div className="hm-support-row">
          <Icon name="phone" size={22} />
          {SUPPORT_PHONE ? (
            <a className="hm-support-link" href={`tel:${SUPPORT_PHONE.replace(/[^\d+]/g, "")}`}>
              {SUPPORT_PHONE}
            </a>
          ) : (
            <span className="hm-support-unset">Phone number not set yet</span>
          )}
        </div>

        <p className="hm-support-foot">Contact details are set by the Super admin.</p>
      </section>
    </PageShell>
  );
}

// ---------- My reports / My suggested places ----------
const KEPT_NOTE = "This list is kept on this phone. Clearing your browser data removes it.";

// The list of reports sent from this phone (used by the phone tab and the desktop page).
function ReportsList({ reports }: { reports: MyReport[] }) {
  const [now] = useState(() => Date.now());
  if (reports.length === 0) return <p className="hm-empty-page">You have not sent any reports from this phone.</p>;
  return (
    <ul className="hm-items">
      {reports.map((r, i) => (
        <li className="hm-item" key={`${r.savedAt}-${i}`}>
          <div className="hm-item-top">
            <span className="hm-item-tag">{r.mode === "help" ? "Needs help" : "Hazard"}</span>
            <span className="hm-item-status">Saved on this phone</span>
          </div>
          <p className="hm-item-title">{r.kind || "Report"}</p>
          {r.savedAt && <p className="hm-item-meta">Sent {timeAgo(r.savedAt, now)}</p>}
        </li>
      ))}
    </ul>
  );
}

// The list of evacuation centers added from this phone.
function PlacesList({ places }: { places: MyPlace[] }) {
  const [now] = useState(() => Date.now());
  if (places.length === 0) return <p className="hm-empty-page">You have not added any evacuation centers from this phone.</p>;
  return (
    <ul className="hm-items">
      {places.map((p) => (
        <li className="hm-item" key={p.id}>
          <div className="hm-item-top">
            <span className="hm-item-tag">{p.kind}</span>
            <span className="hm-item-status">On the map</span>
          </div>
          <p className="hm-item-title">{p.name}</p>
          {p.savedAt && <p className="hm-item-meta">Added {timeAgo(p.savedAt, now)}</p>}
        </li>
      ))}
    </ul>
  );
}

// Desktop: My Reports (its own page, no tabs)
export function MyReportsPage({ reports, onBack }: { reports: MyReport[]; onBack: () => void }) {
  return (
    <PageShell title="My Reports" onBack={onBack}>
      <h3 className="hm-section-title">Reports you sent</h3>
      <ReportsList reports={reports} />
      <p className="hm-note hm-note-page">{KEPT_NOTE}</p>
    </PageShell>
  );
}

// Desktop: My Suggested Places (its own page, no tabs)
export function MyPlacesPage({ places, onBack }: { places: MyPlace[]; onBack: () => void }) {
  return (
    <PageShell title="My Suggested Places" onBack={onBack}>
      <h3 className="hm-section-title">Places you suggested</h3>
      <PlacesList places={places} />
      <p className="hm-note hm-note-page">{KEPT_NOTE}</p>
    </PageShell>
  );
}

// Phone: My Suggested Places and Reports (one page, two tabs)
export function MyActivityPage({
  reports,
  places,
  onBack,
}: {
  reports: MyReport[];
  places: MyPlace[];
  onBack: () => void;
}) {
  const [tab, setTab] = useState<"reports" | "places">("reports");

  return (
    <PageShell title="My reports and places" onBack={onBack}>
      <div className="hm-tabs" role="tablist" aria-label="My reports and places">
        <button
          type="button"
          role="tab"
          id="hm-tab-reports"
          aria-selected={tab === "reports"}
          aria-controls="hm-panel"
          className="hm-tab"
          onClick={() => setTab("reports")}
        >
          Reports <span className="hm-tab-count">{reports.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          id="hm-tab-places"
          aria-selected={tab === "places"}
          aria-controls="hm-panel"
          className="hm-tab"
          onClick={() => setTab("places")}
        >
          Places <span className="hm-tab-count">{places.length}</span>
        </button>
      </div>

      <div id="hm-panel" role="tabpanel" aria-labelledby={tab === "reports" ? "hm-tab-reports" : "hm-tab-places"}>
        {tab === "reports" ? <ReportsList reports={reports} /> : <PlacesList places={places} />}
        <p className="hm-note hm-note-page">{KEPT_NOTE}</p>
      </div>
    </PageShell>
  );
}