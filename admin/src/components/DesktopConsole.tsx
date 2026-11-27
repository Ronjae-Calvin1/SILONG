import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "../auth";
import logo from "../assets/silong-logo-white.png";
import LiveMapPage from "./LiveMapPage";

const COMING: { path: string; label: string; text: string }[] = [
  { path: "places", label: "Places", text: "Coming next" },
  { path: "content", label: "Content", text: "Coming next" },
  { path: "chatbot", label: "Chatbot", text: "Planned" },
  { path: "accounts", label: "Accounts", text: "Coming next" },
];

export default function DesktopConsole() {
  const { user, signOut } = useAuth();
  return (
    <div className="shell">
      <header className="topbar">
        <img className="topbar-logo" src={logo} alt="SILONG" />
        <span className="badge-admin">ADMIN</span>
        <nav className="tabs" aria-label="Admin sections">
          <NavLink to="/live-map">Live map</NavLink>
          {COMING.map((c) => (
            <NavLink key={c.path} to={`/${c.path}`}>
              {c.label}
            </NavLink>
          ))}
        </nav>
        <span className="topbar-name">{user?.name}</span>
        <button className="btn btn-signout" onClick={signOut}>
          Sign out
        </button>
      </header>
      <main className="shell-main">
        <Routes>
          <Route path="/" element={<Navigate to="/live-map" replace />} />
          <Route path="/live-map" element={<LiveMapPage />} />
          {COMING.map((c) => (
            <Route
              key={c.path}
              path={`/${c.path}`}
              element={
                <div className="coming">
                  <h1>{c.label}</h1>
                  <p>{c.text}</p>
                </div>
              }
            />
          ))}
          <Route path="*" element={<Navigate to="/live-map" replace />} />
        </Routes>
      </main>
    </div>
  );
}
