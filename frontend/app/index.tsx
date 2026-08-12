import { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet, Pressable } from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { colors, radius, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { useAuth } from '@/src/auth-context';

/**
 * Cold-start gateway.
 *
 * Expo Router mounts this file for the URL `/`. The whole point of this route
 * is to decide as fast as possible whether the user is signed in and hand off
 * to `/(auth)/sign-in` or `/(tabs)`. If auth bootstrap resolves quickly, we
 * `<Redirect />` synchronously and the user never sees this screen.
 *
 * The two failure modes we defend against — and the reason this component
 * exists at all — are:
 *   1. `getAccessToken()` (SecureStore) hangs on Android production builds
 *   2. `api.me()` times out because the baked-in EXPO_PUBLIC_BACKEND_URL is
 *      unreachable at the moment the user opens the app
 * If either happens, `loading` stays `true` for many seconds. Rather than
 * showing an unbranded infinite spinner, we auto-navigate to sign-in after
 * a short grace period and surface a "Continue" escape hatch so a frustrated
 * user can bail out on their own.
 */
export default function Index() {
  useTheme();
  const { user, loading } = useAuth();
  const router = useRouter();
  const [showEscape, setShowEscape] = useState(false);

  useEffect(() => {
    // If bootstrap is still loading after 2.5s, offer manual navigation.
    const escape = setTimeout(() => setShowEscape(true), 2500);
    // Belt-and-braces: after 5s, force-navigate to sign-in no matter what
    // auth state says. `router.replace` is idempotent so this is safe even
    // if the auth-resolved redirect just happened.
    const forceNav = setTimeout(() => {
      if (loading) router.replace('/(auth)/sign-in');
    }, 5000);
    return () => {
      clearTimeout(escape);
      clearTimeout(forceNav);
    };
    // Intentionally exclude `loading` to keep the timers stable across renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  // Fast path: auth bootstrap already resolved → immediate redirect.
  if (!loading) {
    return user ? <Redirect href="/(tabs)" /> : <Redirect href="/(auth)/sign-in" />;
  }

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <ActivityIndicator size="large" color={colors.brandPrimary} />
        <Text style={styles.brand}>TeeBox</Text>
        <Text style={styles.hint}>Warming up…</Text>
      </View>

      {showEscape ? (
        <Pressable
          testID="index-continue"
          onPress={() => router.replace('/(auth)/sign-in')}
          style={styles.escape}
        >
          <Text style={styles.escapeText}>Continue to sign in</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  card: { alignItems: 'center', gap: spacing.md },
  brand: { fontSize: 22, fontWeight: '900', color: colors.brandPrimary, letterSpacing: 0.5 },
  hint: { fontSize: 13, color: colors.muted },
  escape: {
    position: 'absolute',
    bottom: 60,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  escapeText: { color: '#fff', fontWeight: '800', fontSize: 14 },
}));
