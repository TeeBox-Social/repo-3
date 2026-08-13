import { Stack, useRouter, useSegments, useRootNavigationState } from 'expo-router';
import * as Linking from 'expo-linking';
import * as SplashScreen from 'expo-splash-screen';
import React, { useEffect, useState } from 'react';
import { LogBox, Platform, StatusBar, View, Text, Pressable } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { KeyboardProvider } from 'react-native-keyboard-controller';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { useIconFonts } from '@/src/hooks/use-icon-fonts';
import { AuthProvider, useAuth } from '@/src/auth-context';
import { ThemeProvider, useTheme } from '@/src/theme-context';
import { initAdMob } from '@/src/components/FeedNativeAd';

// Keep LogBox on so genuine errors surface — the previous ignoreAllLogs was
// hiding startup crashes on Expo Go and left users with a blank splash.
LogBox.ignoreLogs([
  'shadow* style props',
  'props.pointerEvents',
]);

// ---- Emergency error boundary --------------------------------------------
// If ANYTHING throws in the tree (native module missing, worklet init, etc.)
// we surface a readable message + a reload prompt instead of leaving the user
// looking at a blank native splash for 30+ seconds.
class RootErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { err: Error | null }
> {
  state = { err: null as Error | null };
  static getDerivedStateFromError(err: Error) {
    return { err };
  }
  componentDidCatch(err: Error) {
    console.warn('[RootErrorBoundary]', err?.message, err?.stack);
  }
  render() {
    if (this.state.err) {
      return (
        <View style={{ flex: 1, backgroundColor: '#0b1f14', padding: 24, justifyContent: 'center' }}>
          <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800', marginBottom: 12 }}>
            TeeBox hit a startup error
          </Text>
          <Text style={{ color: '#c9e5d3', fontSize: 13, marginBottom: 20 }}>
            {String(this.state.err?.message || this.state.err)}
          </Text>
          <Pressable
            onPress={() => this.setState({ err: null })}
            style={{ backgroundColor: '#22c55e', paddingVertical: 14, borderRadius: 12, alignItems: 'center' }}
          >
            <Text style={{ color: '#fff', fontWeight: '700' }}>Retry</Text>
          </Pressable>
        </View>
      );
    }
    return this.props.children;
  }
}

// Keep the native splash visible from cold start until icon fonts register.
// Required because @expo/vector-icons' componentDidMount fallback fires
// Font.loadAsync against a broken vendor path if any <Icon> mounts before
// the family is registered — which throws on Android Expo Go.
try {
  SplashScreen.preventAutoHideAsync();
} catch {
  // Native module can throw on hot reloads / dev builds — safe to ignore.
}

function ProtectedRouter() {
  const { user, loading, signInWithGoogleSession } = useAuth();
  const { colors } = useTheme();
  const segments = useSegments();
  const router = useRouter();
  const navState = useRootNavigationState();

  useEffect(() => {
    // Wait for the navigator to mount, but no longer block on `loading` — the
    // gateway `/app/index.tsx` handles the loading state visually itself, and
    // for every other route we want redirects to fire immediately based on
    // whatever the current auth snapshot is. Blocking here was one of the
    // reasons a stuck bootstrap could freeze the whole app.
    if (!navState?.key) return;
    if (loading) return; // still let the loading spinner show on /
    const inAuth = segments[0] === '(auth)';
    const onGateway = segments.length === 0; // "/" route
    // Public flows reachable via email links even when signed-out.
    const isPublicRoute =
      segments[0] === 'reset-password' || segments[0] === 'verify-email';
    if (!user && !inAuth && !onGateway && !isPublicRoute) {
      router.replace('/(auth)/sign-in');
    } else if (user && inAuth) {
      router.replace('/(tabs)');
    }
  }, [user, loading, segments, navState?.key, router]);

  // Handle share-intent + auth deep links:
  //   teebox://share?course=...&score=82&par=72&notes=...
  //   teebox://reset-password?token=...
  //   teebox://verify-email?token=...
  //   teebox://auth#session_id=...  (Emergent Google redirect on mobile)
  useEffect(() => {
    const parse = (url: string | null) => {
      if (!url) return;
      try {
        // session_id lives in the hash fragment; Linking.parse strips it.
        const sidMatch = url.match(/[#?&]session_id=([^&]+)/);
        const sessionId = sidMatch ? decodeURIComponent(sidMatch[1]) : null;
        const parsed = Linking.parse(url);
        const target = parsed.hostname || parsed.path || '';
        const q = parsed.queryParams || {};
        if (sessionId && (target === 'auth' || target === '' || target === '/')) {
          signInWithGoogleSession(sessionId).catch(() => {});
          return;
        }
        if (target === 'share' && user) {
          router.push({ pathname: '/(tabs)/log', params: q as any });
        } else if (target === 'reset-password') {
          router.push({ pathname: '/reset-password' as any, params: q as any });
        } else if (target === 'verify-email') {
          router.push({ pathname: '/verify-email' as any, params: q as any });
        }
      } catch {}
    };
    Linking.getInitialURL().then(parse);
    const sub = Linking.addEventListener('url', (e) => parse(e.url));
    return () => sub.remove();
  }, [user, router, signInWithGoogleSession]);

  // ---- Web-only Google OAuth redirect handler ----
  // Emergent OAuth redirects back to `<origin>/#session_id=...`. We must
  // process that ONCE on mount before the router bounces us to /sign-in.
  useEffect(() => {
    // Hard-gate to web. On Hermes/React Native the `window` global IS defined
    // (polyfilled) but `window.location` is undefined, so `window.location.search`
    // throws "Cannot read property 'search' of undefined" and crashes app boot.
    if (Platform.OS !== 'web') return;
    if (typeof window === 'undefined' || !window.location) return;
    const search = window.location.search || '';
    const hash = window.location.hash || '';
    const combined = search + '&' + hash;
    const m = combined.match(/[#?&]session_id=([^&]+)/);
    if (!m) return;
    const sessionId = decodeURIComponent(m[1]);
    try {
      window.history.replaceState(null, '', window.location.pathname);
    } catch {}
    signInWithGoogleSession(sessionId).catch((e) => {
      console.warn('Google sign-in failed:', e?.message || e);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }}>
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="post/[id]" options={{ presentation: 'card' }} />
      <Stack.Screen name="user/[id]" options={{ presentation: 'card' }} />
      <Stack.Screen name="user/[id]/friends" options={{ presentation: 'card' }} />
      <Stack.Screen name="course/[name]" options={{ presentation: 'card' }} />
      <Stack.Screen name="profile/edit" options={{ presentation: 'modal' }} />
      <Stack.Screen name="profile/admin/courses" options={{ presentation: 'card' }} />
      <Stack.Screen name="settings" options={{ presentation: 'card' }} />
      <Stack.Screen name="premium" options={{ presentation: 'card' }} />
      <Stack.Screen name="notifications" options={{ presentation: 'card' }} />
      <Stack.Screen name="reset-password" options={{ presentation: 'card' }} />
      <Stack.Screen name="verify-email" options={{ presentation: 'card' }} />
    </Stack>
  );
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();
  // Absolute last-resort escape hatch: if font loading neither resolves nor
  // errors within 4s (e.g. a hung network on a real device), render anyway so
  // the app can never get stuck on the native splash forever. On Expo Go the
  // CDN fonts normally register in well under 2s; on web the map is empty and
  // `loaded` is true on first render.
  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setTimedOut(true), 4000);
    return () => clearTimeout(t);
  }, []);

  // Gate the whole tree on font readiness. This is the critical fix for the
  // Expo Go "Font file for ionicons is empty" crash: we must NOT mount any
  // <Ionicons> (sign-in eye toggle, tab bar, etc.) until the icon font family
  // is registered. If an icon mounts first, @expo/vector-icons auto-loads the
  // local .ttf which Metro serves as 0 bytes on Expo Go Android → the promise
  // rejects and the render tree blanks out (the error overlay is suppressed by
  // LogBox.ignoreAllLogs, so the user just sees a white screen).
  const ready = loaded || !!error || timedOut;

  // Hide the native splash UNCONDITIONALLY on mount after a short delay. Even
  // if `ready` never flips (e.g. font hook wedged), we never want the user
  // stuck on a black/branded splash screen with no way out — the RN JS tree
  // below can render its own fallback / sign-in.
  useEffect(() => {
    const t = setTimeout(() => {
      SplashScreen.hideAsync().catch(() => {});
    }, 1500);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (ready) {
      SplashScreen.hideAsync().catch(() => {});
    }
  }, [ready]);

  // Initialize AdMob SDK once per app session. Best-effort: no-op on web /
  // Expo Go where the native module isn't present.
  useEffect(() => {
    initAdMob().catch(() => {});
  }, []);

  // Keep the native splash up (return null) until fonts are ready. The splash
  // is force-retracted via the effect above the instant `ready` flips true.
  if (!ready) {
    return null;
  }

  return (
    <RootErrorBoundary>
      <GestureHandlerRootView style={{ flex: 1 }}>
        <KeyboardProvider>
          <SafeAreaProvider>
            <ThemeProvider>
              <ThemedStatusBar />
              <AuthProvider>
                <ProtectedRouter />
              </AuthProvider>
            </ThemeProvider>
          </SafeAreaProvider>
        </KeyboardProvider>
      </GestureHandlerRootView>
    </RootErrorBoundary>
  );
}

function ThemedStatusBar() {
  const { scheme } = useTheme();
  return <StatusBar barStyle={scheme === 'dark' ? 'light-content' : 'dark-content'} />;
}
