// TeeBox design tokens - mirror of design_guidelines.json for RN.
import { Platform } from 'react-native';

const lightPalette = {
  surface: '#FDFCF8',
  onSurface: '#1A1D1C',
  surfaceSecondary: '#FFFFFF',
  onSurfaceSecondary: '#1A1D1C',
  surfaceTertiary: '#F2F1E8',
  onSurfaceTertiary: '#4B5563',
  surfaceInverse: '#132A1C',
  onSurfaceInverse: '#FFFFFF',
  brand: '#15803D',
  brandPrimary: '#15803D',
  brandDeep: '#0E5F2C',
  onBrandPrimary: '#FFFFFF',
  brandSecondary: '#D97706',
  onBrandSecondary: '#FFFFFF',
  brandTertiary: '#DCFCE7',
  onBrandTertiary: '#14532D',
  success: '#16A34A',
  warning: '#F59E0B',
  error: '#DC2626',
  border: '#E4E3DB',
  borderStrong: '#BDBBAE',
  divider: '#E4E3DB',
  muted: '#6B7161',
};

export type Colors = typeof lightPalette;

// Dark palette — same token keys so any StyleSheet built from the palette works
// unchanged. Values chosen for a warm, high-contrast fairway-green dark theme.
export const darkColors: Colors = {
  surface: '#0F1512',
  onSurface: '#F1F3EF',
  surfaceSecondary: '#18201B',
  onSurfaceSecondary: '#F1F3EF',
  surfaceTertiary: '#222B24',
  onSurfaceTertiary: '#C4CBC2',
  surfaceInverse: '#0A2314',
  onSurfaceInverse: '#FFFFFF',
  brand: '#2FA95A',
  brandPrimary: '#2FA95A',
  brandDeep: '#1C7A3E',
  onBrandPrimary: '#06130B',
  brandSecondary: '#F59E0B',
  onBrandSecondary: '#1A1204',
  brandTertiary: '#12351F',
  onBrandTertiary: '#9DE9BB',
  success: '#22C55E',
  warning: '#F59E0B',
  error: '#F87171',
  border: '#2C352E',
  borderStrong: '#3C463E',
  divider: '#2C352E',
  muted: '#98A093',
};

export const lightColors: Colors = lightPalette;

// Mutable active-theme pointer. `setActiveScheme` is called by the ThemeProvider
// whenever the resolved scheme changes, BEFORE children re-render, so the Proxies
// below always resolve to the correct palette during render.
const _active: { scheme: 'light' | 'dark'; palette: Colors } = {
  scheme: 'light',
  palette: lightPalette,
};

export function setActiveScheme(scheme: 'light' | 'dark') {
  _active.scheme = scheme;
  _active.palette = scheme === 'dark' ? darkColors : lightPalette;
}

// `colors` resolves each property at ACCESS time against the active palette.
// Inline usages (e.g. <Icon color={colors.muted} />) therefore update on the
// next render after a theme change — no per-file edits required.
export const colors: Colors = new Proxy({} as Colors, {
  get: (_t, prop) => (_active.palette as any)[prop as any],
  set: () => true,
}) as Colors;

// Build a StyleSheet that swaps between pre-computed light/dark variants at
// property-access time. Usage:
//   const styles = makeThemedSheet((colors) => StyleSheet.create({ ... }));
export function makeThemedSheet<T extends Record<string, any>>(factory: (c: Colors) => T): T {
  const light = factory(lightPalette);
  const dark = factory(darkColors);
  return new Proxy({} as T, {
    get: (_t, prop) => (_active.scheme === 'dark' ? dark : light)[prop as any],
  }) as T;
}

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
};

export const radius = {
  sm: 6,
  md: 12,
  lg: 20,
  pill: 999,
};

// Cross-platform shadow presets.
//
// RN Web (0.76+) deprecates the individual `shadow*` style props in favour of
// CSS-style `boxShadow`. Native (iOS) still needs the `shadow*` triple + Android
// still needs `elevation`. `Platform.select` gives us both without triggering
// the web deprecation warnings.
const shadowCard = Platform.select({
  web: {
    boxShadow: '0px 6px 14px rgba(11, 58, 32, 0.08)',
  },
  default: {
    shadowColor: '#0B3A20',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.08,
    shadowRadius: 14,
    elevation: 4,
  },
}) as any;

const shadowSoft = Platform.select({
  web: {
    boxShadow: '0px 2px 6px rgba(11, 58, 32, 0.06)',
  },
  default: {
    shadowColor: '#0B3A20',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
}) as any;

const shadowFloating = Platform.select({
  web: {
    boxShadow: '0px 10px 22px rgba(11, 58, 32, 0.18)',
  },
  default: {
    shadowColor: '#0B3A20',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.18,
    shadowRadius: 22,
    elevation: 10,
  },
}) as any;

export const shadow = {
  card: shadowCard,
  soft: shadowSoft,
  floating: shadowFloating,
};

export const fonts = {
  display: 'System',
  text: 'System',
};

export const IMAGES = {
  authHero:
    'https://images.unsplash.com/photo-1629673120178-53a664eec9e8?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzN8MHwxfHNlYXJjaHwxfHxmcmllbmRzJTIwcGxheWluZyUyMGdvbGYlMjBjb3Vyc2UlMjBzbWlsaW5nfGVufDB8fHx8MTc4MzIwNDk4OXww&ixlib=rb-4.1.0&q=85',
  emptyFeed:
    'https://images.unsplash.com/photo-1517074009205-d9ca5d8b4a63?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1ODF8MHwxfHNlYXJjaHwxfHxlbXB0eSUyMGdvbGYlMjBncmVlbiUyMGZsYWclMjBob2xlfGVufDB8fHx8MTc4MzIwNDk4OXww&ixlib=rb-4.1.0&q=85',
  courseThumb:
    'https://images.unsplash.com/photo-1592937238247-cd0090e02f65?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NTJ8MHwxfHNlYXJjaHwxfHxmYW1vdXMlMjBiZWF1dGlmdWwlMjBnb2xmJTIwY291cnNlJTIwbGFuZHNjYXBlfGVufDB8fHx8MTc4MzIwNDk4OXww&ixlib=rb-4.1.0&q=85',
};
