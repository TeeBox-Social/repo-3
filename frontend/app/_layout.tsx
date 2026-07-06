import { Stack, useRouter, useSegments, useRootNavigationState } from 'expo-router';
import * as Linking from 'expo-linking';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { LogBox, StatusBar } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { useIconFonts } from '@/src/hooks/use-icon-fonts';
import { AuthProvider, useAuth } from '@/src/auth-context';

LogBox.ignoreAllLogs(true);

// Keep the native splash visible from cold start until icon fonts register.
// Required because @expo/vector-icons' componentDidMount fallback fires
// Font.loadAsync against a broken vendor path if any <Icon> mounts before
// the family is registered — which throws on Android Expo Go.
SplashScreen.preventAutoHideAsync();

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
    </Stack>
  );
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();

  useEffect(() => {
    if (loaded || error) {
      SplashScreen.hideAsync();
    }
  }, [loaded, error]);

  if (!loaded && !error) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <StatusBar barStyle="dark-content" />
        <AuthProvider>
          <ProtectedRouter />
        </AuthProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
