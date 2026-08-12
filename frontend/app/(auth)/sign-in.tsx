import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Dimensions,
  Pressable,
  KeyboardAvoidingView,
  ScrollView,
  Platform,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, IMAGES, radius, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { GoogleSignInButton } from '@/src/components/GoogleSignInButton';
import { useAuth } from '@/src/auth-context';

const { height } = Dimensions.get('window');
const HERO_H = Math.round(height * 0.42);
// Lift hero copy up out of the gradient's fade-to-white band so no text ever
// sits in the washed-out portion where the hero blends into the form surface.
const HERO_COPY_BOTTOM = Math.round(HERO_H * 0.3);

// Storage keys for the Remember-me feature. Loaded lazily via a require() so
// that if the storage module fails to load for any reason (bad native module
// linking on Android, etc.) the sign-in screen still renders — the user just
// won't get credential persistence until the next build.
const REMEMBER_FLAG_KEY = 'teebox_remember_me';
const REMEMBER_EMAIL_KEY = 'teebox_remember_email';
const REMEMBER_PASSWORD_KEY = 'teebox_remember_password';

// Best-effort storage adapter. Safe even if the native module isn't available.
async function safeGetRemembered(): Promise<{ email: string; password: string } | null> {
  try {
    // Lazy dynamic import — if this throws, we just return null and the form renders empty.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require('@/src/utils/storage');
    const s = mod?.storage;
    if (!s) return null;
    const flag = await s.getItem(REMEMBER_FLAG_KEY, null);
    if (flag !== '1') return null;
    const email = await s.getItem(REMEMBER_EMAIL_KEY, null);
    const password = await s.secureGet(REMEMBER_PASSWORD_KEY, null);
    return {
      email: email ? String(email) : '',
      password: password ? String(password) : '',
    };
  } catch {
    return null;
  }
}

async function safeSaveRemembered(email: string, password: string, remember: boolean) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require('@/src/utils/storage');
    const s = mod?.storage;
    if (!s) return;
    if (remember) {
      await s.setItem(REMEMBER_FLAG_KEY, '1');
      await s.setItem(REMEMBER_EMAIL_KEY, email);
      await s.secureSet(REMEMBER_PASSWORD_KEY, password);
    } else {
      await s.removeItem(REMEMBER_FLAG_KEY);
      await s.removeItem(REMEMBER_EMAIL_KEY);
      await s.secureRemove(REMEMBER_PASSWORD_KEY);
    }
  } catch {
    // Best-effort: never let a storage hiccup block the sign-in flow
  }
}

export default function SignIn() {
  useTheme();
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Hydrate any remembered credentials from prior sessions. Fully defensive —
  // any exception here is swallowed so the form never fails to render.
  useEffect(() => {
    let alive = true;
    safeGetRemembered().then((remembered) => {
      if (!alive || !remembered) return;
      if (remembered.email) setEmail(remembered.email);
      if (remembered.password) setPassword(remembered.password);
      setRememberMe(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  const onSubmit = async () => {
    setErr(null);
    if (!email.trim() || !password) {
      setErr('Please enter your email and password.');
      return;
    }
    setLoading(true);
    try {
      await signIn(email.trim(), password);
      // Only persist AFTER the login succeeds — never store a bad password.
      await safeSaveRemembered(email.trim(), password, rememberMe);
    } catch (e: any) {
      // Surface the actual error so the user knows what went wrong instead of
      // silently failing. Includes network errors ("Failed to fetch" style),
      // auth errors ("Invalid email or password"), and rate limits.
      const msg = e?.message || String(e) || 'Login failed';
      setErr(
        /Failed to fetch|Network request failed|aborted|AbortError/i.test(msg)
          ? 'Cannot reach the TeeBox server. Check your internet connection and try again.'
          : msg,
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container} testID="sign-in-screen">
      <View style={[styles.hero, { height: HERO_H }]}>
        <Image source={{ uri: IMAGES.authHero }} style={StyleSheet.absoluteFillObject} contentFit="cover" />
        <LinearGradient
          colors={['rgba(19,42,28,0.15)', 'rgba(19,42,28,0.45)', colors.surface]}
          locations={[0, 0.7, 1]}
          style={StyleSheet.absoluteFillObject}
        />
        <View style={styles.heroCopy}>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>TEEBOX</Text>
          </View>
          <Text style={styles.heroTitle}>TeeBox Social</Text>
          <Text style={styles.heroSub}>Log rounds, review courses, and keep the group chat rolling.</Text>
        </View>
      </View>

      {/* Using core RN KeyboardAvoidingView + ScrollView (no third-party native
          module required) so the sign-in screen has zero risk of a native
          linking issue rendering it blank on Android release builds. */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView
          contentContainerStyle={styles.form}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.formTitle}>Welcome back</Text>
          <TBInput
            label="Email"
            testID="sign-in-email"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            placeholder="you@teebox.com"
          />
          <TBInput
            label="Password"
            testID="sign-in-password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry={!showPassword}
            autoComplete="password"
            placeholder="At least 6 characters"
            rightAdornment={
              <Pressable
                testID="sign-in-toggle-password"
                onPress={() => setShowPassword((v) => !v)}
                hitSlop={10}
                style={styles.eyeBtn}
              >
                <Ionicons
                  name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                  size={20}
                  color={colors.muted}
                />
              </Pressable>
            }
          />
          <Pressable
            testID="sign-in-remember-me"
            onPress={() => setRememberMe((v) => !v)}
            style={styles.rememberRow}
            hitSlop={8}
          >
            <View style={[styles.checkbox, rememberMe && styles.checkboxOn]}>
              {rememberMe ? <Ionicons name="checkmark" size={14} color="#fff" /> : null}
            </View>
            <Text style={styles.rememberText}>Remember me on this device</Text>
          </Pressable>
          {err ? (
            <Text style={styles.errText} testID="sign-in-error">
              {err}
            </Text>
          ) : null}
          <TBButton
            label="Sign in"
            testID="sign-in-submit"
            loading={loading}
            onPress={onSubmit}
            style={{ marginTop: spacing.md }}
          />
          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or</Text>
            <View style={styles.dividerLine} />
          </View>
          <GoogleSignInButton
            testID="sign-in-google"
            onError={(msg) => setErr(msg)}
          />
          <Pressable
            testID="sign-in-forgot-password"
            onPress={() => router.push('/(auth)/forgot-password' as any)}
            style={{ marginTop: spacing.md, alignSelf: 'center' }}
            hitSlop={8}
          >
            <Text style={styles.forgotText}>Forgot your password?</Text>
          </Pressable>
          <Pressable
            testID="sign-in-go-signup"
            onPress={() => router.push('/(auth)/sign-up')}
            style={{ marginTop: spacing.lg, alignSelf: 'center' }}
          >
            <Text style={styles.linkText}>
              New to TeeBox? <Text style={styles.linkStrong}>Create an account</Text>
            </Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  hero: { justifyContent: 'flex-end' },
  heroCopy: { padding: spacing.xl, paddingBottom: HERO_COPY_BOTTOM, gap: spacing.sm },
  badge: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(255,255,255,0.94)',
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
  },
  badgeText: { fontSize: 11, fontWeight: '800', color: colors.brandDeep, letterSpacing: 2 },
  heroTitle: { color: '#fff', fontSize: 32, fontWeight: '800', lineHeight: 36 },
  heroSub: { color: '#EDECDF', fontSize: 15, fontWeight: '600', maxWidth: 320 },
  form: { padding: spacing.xl, gap: spacing.md, paddingBottom: spacing.xxxl },
  formTitle: { fontSize: 24, fontWeight: '800', color: colors.onSurface, marginBottom: spacing.md },
  errText: { color: colors.error, fontWeight: '700', fontSize: 13, marginTop: -4 },
  linkText: { fontSize: 14, color: colors.muted },
  linkStrong: { color: colors.brandPrimary, fontWeight: '800' },
  forgotText: { fontSize: 14, color: colors.brandPrimary, fontWeight: '700' },
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  dividerLine: { flex: 1, height: 1, backgroundColor: colors.divider },
  dividerText: { fontSize: 12, fontWeight: '700', color: colors.muted, letterSpacing: 0.6 },
  eyeBtn: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rememberRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginTop: 4,
    paddingVertical: 4,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 5,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxOn: {
    backgroundColor: colors.brandPrimary,
    borderColor: colors.brandPrimary,
  },
  rememberText: { fontSize: 14, color: colors.onSurface, fontWeight: '600' },
}));
