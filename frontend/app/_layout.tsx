import { Stack, useRouter, useSegments, useRootNavigationState } from 'expo-router';
import * as Linking from 'expo-linking';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { LogBox, StatusBar } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { KeyboardProvider } from 'react-native-keyboard-controller';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { useIconFonts } from '@/src/hooks/use-icon-fonts';
import { AuthProvider, useAuth } from '@/src/auth-context';

LogBox.ignoreAllLogs(true);

// Keep the native splash visible from cold start until icon fonts register.
// Required because @expo/vector-icons' componentDidMount fallback fires
// Font.loadAsync against a broken vendor path if any <Icon> mounts before
// the family is registered — which throws on Android Expo Go.
try {
  SplashScreen.preventAutoHideAsync();
} catch {
  // Native module can throw on hot reloads / dev builds — safe to ignore.
}

// Hard safety net: force-hide the native splash after 2s. The React tree
// takes over from there — the gateway route (`app/index.tsx`) shows a branded
// "Warming up" state and self-navigates to sign-in after 5s max. Two seconds
// is short enough that the user never wonders if the app died, and long enough
// for the JS bundle to parse on mid-range Android devices.
setTimeout(() => {
  SplashScreen.hideAsync().catch(() => {});
}, 2000);

function ProtectedRouter() {
  const { user, loading } = useAuth();
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
  useEffect(() => {
    const parse = (url: string | null) => {
      if (!url) return;
      try {
        const parsed = Linking.parse(url);
        const target = parsed.hostname || parsed.path || '';
        const q = parsed.queryParams || {};
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
  }, [user, router]);

  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#FDFCF8' } }}>
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="post/[id]" options={{ presentation: 'card' }} />
      <Stack.Screen name="user/[id]" options={{ presentation: 'card' }} />
      <Stack.Screen name="user/[id]/friends" options={{ presentation: 'card' }} />
      <Stack.Screen name="course/[name]" options={{ presentation: 'card' }} />
      <Stack.Screen name="profile/edit" options={{ presentation: 'modal' }} />
      <Stack.Screen name="profile/admin/courses" options={{ presentation: 'card' }} />
      <Stack.Screen name="notifications" options={{ presentation: 'card' }} />
      <Stack.Screen name="reset-password" options={{ presentation: 'card' }} />
      <Stack.Screen name="verify-email" options={{ presentation: 'card' }} />
    </Stack>
  );
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();

  useEffect(() => {
    if (loaded || error) {
      SplashScreen.hideAsync().catch(() => {});
    }
  }, [loaded, error]);

  // Render the tree even while fonts are still loading — the splash timer
  // above will retract the native splash after at most 5s. Falling back to
  // React tree render means users never see an infinite spinner even if the
  // font-loading promise never resolves for some reason.
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <KeyboardProvider>
        <SafeAreaProvider>
          <StatusBar barStyle="dark-content" />
          <AuthProvider>
            <ProtectedRouter />
          </AuthProvider>
        </SafeAreaProvider>
      </KeyboardProvider>
    </GestureHandlerRootView>
  );
}
