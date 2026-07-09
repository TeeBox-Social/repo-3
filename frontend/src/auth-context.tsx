import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  api,
  getAccessToken,
  saveTokens,
  setOnAuthLost,
  User,
} from '@/src/api';

type AuthState = {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (payload: {
    email: string;
    password: string;
    display_name: string;
    home_course?: string;
    handicap?: number;
  }) => Promise<void>;
  signInWithGoogleSession: (session_id: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  setUser: (u: User) => void;
};

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const bootstrap = useCallback(async () => {
    setLoading(true);
    try {
      // Guard SecureStore read against Android production-build hangs. In some
      // signed-release scenarios `SecureStore.getItemAsync` can block forever
      // if the keystore alias is in a weird state after uninstall/reinstall.
      // A 3s ceiling means we never lock the entire app on it.
      const token = await Promise.race([
        getAccessToken(),
        new Promise<string | null>((resolve) => setTimeout(() => resolve(null), 3000)),
      ]);
      if (!token) {
        setUser(null);
      } else {
        // Race /auth/me against a hard 6s ceiling. This prevents the cold-start
        // hang symptom (splash spinner forever) when the backend is unreachable —
        // if the check times out we drop the user to sign-in so they can retry.
        const meResult = await Promise.race([
          api.me().then((u) => ({ ok: true as const, user: u })),
          new Promise<{ ok: false; timeout?: boolean }>((resolve) =>
            setTimeout(() => resolve({ ok: false, timeout: true }), 6000),
          ),
        ]);
        if (meResult.ok) {
          setUser(meResult.user);
        } else {
          // Network-timed-out: keep the token, but leave user null so the
          // ProtectedRouter routes to sign-in. The user can re-attempt login;
          // a subsequent /auth/me success will populate them fully.
          setUser(null);
        }
      }
    } catch {
      // Only clear tokens on definite auth failures (401 handled inside request()).
      // On network errors, keep them for the next attempt.
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // If the refresh flow gives up (invalid / reused refresh), sign the user out
    setOnAuthLost(() => {
      setUser(null);
    });
    bootstrap();
  }, [bootstrap]);

  const signIn = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    await saveTokens(res.access_token, res.refresh_token);
    setUser(res.user);
  }, []);

  const signUp = useCallback(async (payload: Parameters<AuthState['signUp']>[0]) => {
    const res = await api.register(payload);
    await saveTokens(res.access_token, res.refresh_token);
    setUser(res.user);
  }, []);

  const signInWithGoogleSession = useCallback(async (session_id: string) => {
    const res = await api.googleSignIn(session_id);
    await saveTokens(res.access_token, res.refresh_token);
    setUser(res.user);
  }, []);

  const signOut = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      signIn,
      signUp,
      signInWithGoogleSession,
      signOut,
      refresh: bootstrap,
      setUser,
    }),
    [user, loading, signIn, signUp, signInWithGoogleSession, signOut, bootstrap],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
