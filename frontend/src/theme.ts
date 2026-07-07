// TeeBox design tokens - mirror of design_guidelines.json for RN.
import { Platform } from 'react-native';

export const colors = {
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
