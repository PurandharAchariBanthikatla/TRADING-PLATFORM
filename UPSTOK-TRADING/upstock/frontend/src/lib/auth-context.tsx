"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, authApi } from "@/lib/api";
import type { UserPublic } from "@/types/auth";

// Storage note: the refresh token is kept in localStorage and the access
// token only in memory (React state). This is a pragmatic default for the
// first vertical slice; the hardened version swaps the refresh token for an
// httpOnly, SameSite=Strict cookie set directly by the gateway so it's
// unreadable to any JS (defense against XSS token theft) -- tracked as a
// follow-up alongside the security-settings screen.
const REFRESH_TOKEN_STORAGE_KEY = "exchange_refresh_token";

interface AuthContextValue {
  user: UserPublic | null;
  accessToken: string | null;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => setError(null), []);

  const establishSession = useCallback(async (newAccessToken: string, newRefreshToken: string) => {
    localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, newRefreshToken);
    setAccessToken(newAccessToken);
    const profile = await authApi.me(newAccessToken);
    setUser(profile);
  }, []);

  useEffect(() => {
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
    if (!storedRefreshToken) {
      setIsLoading(false);
      return;
    }

    authApi
      .refresh(storedRefreshToken)
      .then((tokens) => establishSession(tokens.access_token, tokens.refresh_token))
      .catch(() => localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY))
      .finally(() => setIsLoading(false));
  }, [establishSession]);

  const login = useCallback(
    async (email: string, password: string) => {
      setError(null);
      try {
        const tokens = await authApi.login(email, password);
        await establishSession(tokens.access_token, tokens.refresh_token);
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : "Unable to sign in right now.");
        throw err;
      }
    },
    [establishSession]
  );

  const register = useCallback(async (email: string, password: string, displayName: string) => {
    setError(null);
    try {
      await authApi.register(email, password, displayName);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Unable to create your account right now.");
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
    localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    setAccessToken(null);
    setUser(null);
    if (storedRefreshToken) {
      await authApi.logout(storedRefreshToken).catch(() => undefined);
    }
  }, []);

  const value = useMemo(
    () => ({ user, accessToken, isLoading, error, login, register, logout, clearError }),
    [user, accessToken, isLoading, error, login, register, logout, clearError]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
