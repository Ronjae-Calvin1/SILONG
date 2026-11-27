import { useEffect, useState, type FormEvent } from "react";
import { ApiError, waitSeconds } from "../api/client";
import { useAuth } from "../auth";
import logo from "../assets/silong-logo-white.png";
import "./SignInPage.css";

export default function SignInPage() {
  const { signIn } = useAuth();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [waitLeft, setWaitLeft] = useState(0); // seconds, after a 429

  useEffect(() => {
    if (waitLeft <= 0) return;
    const t = window.setTimeout(() => setWaitLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(t);
  }, [waitLeft]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy || waitLeft > 0) return;
    setBusy(true);
    setError("");
    try {
      await signIn(name.trim(), password);
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : new ApiError(0, "Can't connect. Check your connection and try again.");
      setError(apiErr.detail); // 401, 423, 429, 422 and 0: the server's text as written
      if (apiErr.status === 429) setWaitLeft(waitSeconds(apiErr.detail) ?? 60);
      setBusy(false);
    }
  }

  return (
    <main className="signin">
      <form className="signin-card" onSubmit={submit}>
        <div className="signin-brand">
          <img src={logo} alt="SILONG" />
          <span className="badge-admin">ADMIN</span>
        </div>
        <h1>Admin sign in</h1>
        <p className="signin-sub">For Admins only.</p>

        <label htmlFor="admin-name">Name</label>
        <input id="admin-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="username" maxLength={100} required />

        <label htmlFor="admin-password">Password</label>
        <div className="signin-pw">
          <input
            id="admin-password"
            type={show ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            maxLength={200}
            required
          />
          <button type="button" className="signin-eye" onClick={() => setShow((s) => !s)} aria-pressed={show}>
            {show ? "Hide" : "Show"}
          </button>
        </div>

        <p className="signin-note">After 5 wrong tries, sign in is locked for 15 minutes.</p>
        {error && (
          <p className="signin-error" role="alert">
            {error}
          </p>
        )}
        <button className="btn btn-primary signin-submit" type="submit" disabled={busy || waitLeft > 0 || !name.trim() || !password}>
          {waitLeft > 0 ? `Wait ${Math.ceil(waitLeft / 60)} min` : busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="signin-foot">No account? Ask an Admin to create one. There is no sign-up.</p>
      </form>
    </main>
  );
}
