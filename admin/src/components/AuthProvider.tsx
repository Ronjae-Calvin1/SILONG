import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError, getToken, setSignedOutHandler, setToken } from "../api/client";
import type { AdminUser } from "../api/types";
import { AuthContext, type AuthStatus } from "../auth";

// Only the person's own clicks, taps and keystrokes count. Polling does not.
const ACTIVITY_EVENTS = ["pointerdown", "keydown", "touchstart"] as const;
const IDLE_CHECK_MS = 10_000;

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(() => (getToken() ? "loading" : "out"));
  const [user, setUser] = useState<AdminUser | null>(null);
  const [expiredDetail, setExpiredDetail] = useState("");
  const lastActive = useRef(0); // time of the person's last click or key press

  const expire = useCallback((detail: string) => {
    setToken(null);
    setUser(null);
    setExpiredDetail(detail);
    setStatus("expired");
  }, []);

  // Any 401 or 403 on an admin call ends the session (the client has already dropped the token).
  useEffect(() => {
    setSignedOutHandler(expire);
    return () => setSignedOutHandler(null);
  }, [expire]);

  // A token kept in sessionStorage across a reload: check it is still good.
  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    api
      .me()
      .then((u) => {
        if (cancelled) return;
        lastActive.current = Date.now();
        setUser(u);
        setStatus("in");
      })
      .catch((e) => {
        // 401/403 already went through expire(). Anything else: show the sign-in.
        if (!cancelled && !(e instanceof ApiError && (e.status === 401 || e.status === 403))) setStatus("out");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (name: string, password: string) => {
    const answer = await api.signIn(name, password);
    setToken(answer.token);
    lastActive.current = Date.now();
    setUser(answer.user);
    setStatus("in");
  }, []);

  const signOut = useCallback(async () => {
    await api.signOut().catch(() => undefined); // safe to call twice; the token is dropped either way
    setToken(null);
    setUser(null);
    setStatus("out");
  }, []);

  const goToSignIn = useCallback(() => setStatus("out"), []);

  // Idle sign-out: after idle_timeout_minutes without the person's own input, sign out and say so.
  useEffect(() => {
    if (status !== "in" || !user) return;
    const limitMs = user.idle_timeout_minutes * 60_000;
    lastActive.current = Date.now();
    const mark = () => {
      lastActive.current = Date.now();
    };
    const check = () => {
      if (Date.now() - lastActive.current < limitMs) return;
      api.signOut().catch(() => undefined);
      expire("You were signed out after " + user.idle_timeout_minutes + " minutes without use.");
    };
    ACTIVITY_EVENTS.forEach((ev) => window.addEventListener(ev, mark, { passive: true }));
    document.addEventListener("visibilitychange", check);
    const timer = window.setInterval(check, IDLE_CHECK_MS);
    return () => {
      ACTIVITY_EVENTS.forEach((ev) => window.removeEventListener(ev, mark));
      document.removeEventListener("visibilitychange", check);
      window.clearInterval(timer);
    };
  }, [status, user, expire]);

  const value = useMemo(
    () => ({ status, user, expiredDetail, signIn, signOut, goToSignIn }),
    [status, user, expiredDetail, signIn, signOut, goToSignIn],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
