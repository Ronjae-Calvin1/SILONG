import { createContext, useContext } from "react";
import type { AdminUser } from "./api/types";

// "loading": checking a token kept from before a reload. "expired": show "You were signed out".
export type AuthStatus = "loading" | "out" | "in" | "expired";

export interface AuthValue {
  status: AuthStatus;
  user: AdminUser | null;
  expiredDetail: string;
  signIn: (name: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  goToSignIn: () => void;
}

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}
