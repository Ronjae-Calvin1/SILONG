import { Link } from "react-router-dom";
import "./AdminSignInPage.css";

// Where the menu's "Admin sign in" goes. Staff accounts (Responders and Super admins) are not built
// yet, so this page says so plainly instead of showing a form that cannot sign anyone in.
export function AdminSignInPage() {
  return (
    <main className="admin-page">
      <div className="admin-card">
        <h1 className="admin-title">Staff sign in</h1>
        <p className="admin-text">
          This page is for Responders and Super admins. Staff sign-in is not available yet.
        </p>
        <p className="admin-text">Everyone else can use the map without signing in.</p>
        <Link className="admin-back" to="/map">
          Back to the map
        </Link>
      </div>
    </main>
  );
}
