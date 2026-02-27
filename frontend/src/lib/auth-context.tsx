"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { getMe, type UserProfile } from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface AuthValue {
  token: string | null;
  user: UserProfile | null;
  loading: boolean;
  signIn: () => void;
  signOut: () => void;
}

export const AuthContext = createContext<AuthValue>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");
    if (urlToken) {
      localStorage.setItem("courtcoach_jwt", urlToken);
      window.history.replaceState({}, "", window.location.pathname);
    }
    const stored = urlToken ?? localStorage.getItem("courtcoach_jwt");
    if (!stored) {
      setLoading(false);
      return;
    }
    setToken(stored);
    getMe(stored)
      .then((u) => setUser(u))
      .catch(() => {
        localStorage.removeItem("courtcoach_jwt");
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem("courtcoach_jwt");
    setToken(null);
    setUser(null);
  }, []);

  const signIn = useCallback(() => {
    window.location.href = `${API_BASE_URL}/auth/google`;
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthContext(): AuthValue {
  return useContext(AuthContext);
}
