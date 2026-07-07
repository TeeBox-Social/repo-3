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

// Hard safety net: force-hide the splash after 5s even if fonts / auth are
// still resolving. This eliminates the "app just spins forever" symptom on
// cold start when the network is unreachable or a native promise never
// resolves. Without this, users would have to reinstall the app.
setTimeout(() => {
  SplashScreen.hideAsync().catch(() => {});
}, 5000);

function ProtectedRouter() {
  const { user, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  const navState = useRootNavigationState();

  useEffect(() => {
    if (loading || !navState?.key) return;
    const inAuth = segments[0] === '(auth)';
    if (!user && !inAuth) {
      router.replace('/(auth)/sign-in');
    } else if (user && inAuth) {
      router.replace('/(tabs)');
    }
  }, [user, loading, segments, navState?.key, router]);

  // Handle share-intent deep links: teebox://share?course=...&score=82&par=72&notes=...
  useEffect(() => {
    if (!user) return;
    const parse = (url: string | null) => {
      if (!url) return;
      try {
        const parsed = Linking.parse(url);
        if (parsed.hostname === 'share' || parsed.path === 'share') {
          const q = parsed.queryParams || {};
          router.push({ pathname: '/(tabs)/log', params: q as any });
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
