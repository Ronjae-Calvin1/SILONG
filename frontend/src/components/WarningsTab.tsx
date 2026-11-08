import { Icon } from "./icons";
import "./AlertsTabs.css";

// Where "View Official Bulletin" goes. Swap in PAGASA's exact bulletin page
// once your team has checked it; this one constant is the only place to change.
const OFFICIAL_BULLETIN_URL = "https://www.pagasa.dost.gov.ph/";

export type WarningsStatus = "loading" | "error" | "unavailable" | "empty" | "ready";

export type WarningItem = {
  id: string;
  title: string;
  details: string;
  organization: string; // who issued it, e.g. "PAGASA"
  issuedAt: Date;
  bulletinUrl?: string | null; // link to the official bulletin, if there is one
};

type Props = {
  status: WarningsStatus;
  errorMessage: string | null;
  warnings?: WarningItem[];
  lastChecked: Date | null; // null = never checked
  onRetry: () => void;
};

function formatDateTime(d: Date): string {
  return d.toLocaleString("en-PH", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function BulletinLink({ url }: { url: string }) {
  return (
    <a className="state-link" href={url} target="_blank" rel="noopener noreferrer">
      View Official Bulletin ↗
    </a>
  );
}

export function WarningsTab({ status, errorMessage, warnings = [], lastChecked, onRetry }: Props) {
  const checkedText = lastChecked ? formatDateTime(lastChecked) : "not yet";

  return (
    <div className="warnings-tab">
      {status === "loading" && (
        <div className="state-box" role="status">
          <strong>Checking for warnings…</strong>
        </div>
      )}

      {status === "error" && (
        <div className="state-box state-box-error" role="alert">
          <strong>Couldn't load warnings</strong>
          <p>{errorMessage ?? "Something went wrong. Please try again."}</p>
          <button className="state-button" onClick={onRetry}>
            Try again
          </button>
          <BulletinLink url={OFFICIAL_BULLETIN_URL} />
        </div>
      )}

      {status === "unavailable" && (
        <div className="state-box">
          <strong>Warnings aren't connected yet</strong>
          <p>
            SILONG can't confirm whether there are official warnings right now. Please check PAGASA
            directly.
          </p>
          <BulletinLink url={OFFICIAL_BULLETIN_URL} />
        </div>
      )}

      {status === "empty" && (
        <div className="empty-card">
          <span className="empty-card-icon">
            <Icon name="warning" size={32} />
          </span>
          <div>
            <strong>No Active Warnings</strong>
            <p>There are currently no official weather warnings issued for Batangas City.</p>
            <p className="warning-meta">Source: PAGASA • Last checked: {checkedText}</p>
            <BulletinLink url={OFFICIAL_BULLETIN_URL} />
          </div>
        </div>
      )}

      {status === "ready" && (
        <ul className="warning-list">
          {warnings.map((w) => (
            <li className="warning-card" key={w.id}>
              <div className="warning-card-head">
                <Icon name="warning" size={22} />
                <strong className="warning-title">{w.title}</strong>
              </div>
              <p className="warning-details">{w.details}</p>
              <p className="warning-meta">
                <span className="warning-badge">Official</span> {w.organization} • {formatDateTime(w.issuedAt)}
              </p>
              <BulletinLink url={w.bulletinUrl ?? OFFICIAL_BULLETIN_URL} />
            </li>
          ))}
        </ul>
      )}

      <p className="alerts-disclaimer">
        Warnings come only from official sources. <strong>Official advisories come first.</strong>
      </p>
    </div>
  );
}