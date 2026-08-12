import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { Appearance } from 'react-native';
import {
  lightColors,
  darkColors,
  setActiveScheme,
  type Colors,
} from '@/src/theme';
import { storage } from '@/src/utils/storage';

export const APPEARANCE_KEY = 'appearance';
export type ThemePreference = 'light' | 'dark' | 'system';
type Scheme = 'light' | 'dark';

type ThemeCtx = {
  colors: Colors;
  scheme: Scheme;
  preference: ThemePreference;
  setPreference: (p: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeCtx>({
  colors: lightColors,
  scheme: 'light',
  preference: 'system',
  setPreference: () => {},
});

function currentSystemScheme(): Scheme {
  return Appearance.getColorScheme() === 'dark' ? 'dark' : 'light';
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPref] = useState<ThemePreference>('system');
  const [sysScheme, setSysScheme] = useState<Scheme>(currentSystemScheme());
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      const saved = await storage.getItem<string>(APPEARANCE_KEY, 'system');
      if (saved === 'light' || saved === 'dark' || saved === 'system') {
        setPref(saved);
      }
      setReady(true);
    })();
  }, []);

  useEffect(() => {
    const sub = Appearance.addChangeListener(({ colorScheme }) => {
      setSysScheme(colorScheme === 'dark' ? 'dark' : 'light');
    });
    return () => sub.remove();
  }, []);

  const setPreference = useCallback((p: ThemePreference) => {
    setPref(p);
    storage.setItem(APPEARANCE_KEY, p).catch(() => {});
  }, []);

  const scheme: Scheme = preference === 'system' ? sysScheme : preference;

  // Point the module-level palette pointers at the resolved scheme BEFORE the
  // children render, so `colors` and `makeThemedSheet` Proxies resolve correctly.
  setActiveScheme(scheme);

  const colors = scheme === 'dark' ? darkColors : lightColors;

  const value = useMemo<ThemeCtx>(
    () => ({ colors, scheme, preference, setPreference }),
    [colors, scheme, preference, setPreference],
  );

  // Avoid a first-paint flash with the wrong theme before storage resolves.
  if (!ready) return null;

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
export const useThemeColors = (): Colors => useContext(ThemeContext).colors;
