import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Dimensions,
  Pressable,
} from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, IMAGES, radius, spacing } from '@/src/theme';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { useAuth } from '@/src/auth-context';
import { storage } from '@/src/utils/storage';

const { height } = Dimensions.get('window');
const HERO_H = Math.round(height * 0.42);

// Storage keys: email is fine in AsyncStorage; password is stored in SecureStore
// via `storage.secureSet` / `storage.secureGet` so it's Keychain/Keystore-encrypted.
const REMEMBER_FLAG_KEY = 'teebox_remember_me';
const REMEMBER_EMAIL_KEY = 'teebox_remember_email';
const REMEMBER_PASSWORD_KEY = 'teebox_remember_password';

export default function SignIn() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Hydrate any remembered credentials from prior sessions
  useEffect(() => {
    (async () => {
      try {
        const flag = await storage.getItem(REMEMBER_FLAG_KEY, null);
        if (flag !== '1') return;
        const savedEmail = await storage.getItem(REMEMBER_EMAIL_KEY, null);
        const savedPw = await storage.secureGet(REMEMBER_PASSWORD_KEY, null);
        if (savedEmail) setEmail(String(savedEmail));
        if (savedPw) setPassword(String(savedPw));
        setRememberMe(true);
      } catch {}
    })();
  }, []);

  const persistRemember = async () => {
    try {
      if (rememberMe) {
        await storage.setItem(REMEMBER_FLAG_KEY, '1');
        await storage.setItem(REMEMBER_EMAIL_KEY, email.trim());
        await storage.secureSet(REMEMBER_PASSWORD_KEY, password);
      } else {
        await storage.removeItem(REMEMBER_FLAG_KEY);
        await storage.removeItem(REMEMBER_EMAIL_KEY);
        await storage.secureRemove(REMEMBER_PASSWORD_KEY);
      }
    } catch {}
  };

  const onSubmit = async () => {
    setErr(null);
    setLoading(true);
    try {
      await signIn(email.trim(), password);
      // Only persist AFTER the login succeeds — never store a bad password.
      await persistRemember();
    } catch (e: any) {
      setErr(e?.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container} testID="sign-in-screen">
      <View style={[styles.hero, { height: HERO_H }]}>
        <Image source={{ uri: IMAGES.authHero }} style={StyleSheet.absoluteFillObject} contentFit="cover" />
        <LinearGradient
          colors={['rgba(19,42,28,0.15)', 'rgba(19,42,28,0.4)', colors.surface]}
          locations={[0, 0.55, 1]}
          style={StyleSheet.absoluteFillObject}
        />
        <View style={styles.heroCopy}>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>TEEBOX</Text>
          </View>
          <Text style={styles.heroTitle}>Your golf, {'\n'}your people.</Text>
          <Text style={styles.heroSub}>Log rounds, review courses, and keep the group chat rolling.</Text>
        </View>
      </View>

      <KeyboardAwareScrollView
        contentContainerStyle={styles.form}
        keyboardShouldPersistTaps="handled"
        bottomOffset={20}
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
          {err ? <Text style={styles.errText}>{err}</Text> : null}
          <TBButton
            label="Sign in"
            testID="sign-in-submit"
            loading={loading}
            onPress={onSubmit}
            style={{ marginTop: spacing.md }}
          />
          <Pressable
            testID="sign-in-go-signup"
            onPress={() => router.push('/(auth)/sign-up')}
            style={{ marginTop: spacing.lg, alignSelf: 'center' }}
          >
            <Text style={styles.linkText}>
              New to TeeBox? <Text style={styles.linkStrong}>Create an account</Text>
            </Text>
          </Pressable>
      </KeyboardAwareScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  hero: { justifyContent: 'flex-end' },
  heroCopy: { padding: spacing.xl, gap: spacing.sm },
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
});
