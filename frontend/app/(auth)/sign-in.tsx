import React, { useState } from 'react';
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
import { colors, IMAGES, radius, spacing } from '@/src/theme';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { useAuth } from '@/src/auth-context';

const { height } = Dimensions.get('window');
const HERO_H = Math.round(height * 0.42);

export default function SignIn() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState('reese@teebox.demo');
  const [password, setPassword] = useState('password123');
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async () => {
    setErr(null);
    setLoading(true);
    try {
      await signIn(email.trim(), password);
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
            keyboardType="email-address"
            placeholder="you@teebox.com"
          />
          <TBInput
            label="Password"
            testID="sign-in-password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholder="At least 6 characters"
          />
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
          <Text style={styles.demoHint}>
            Demo: reese@teebox.demo · password123
          </Text>
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
  demoHint: { textAlign: 'center', color: colors.muted, fontSize: 12, marginTop: spacing.lg, fontStyle: 'italic' },
});
