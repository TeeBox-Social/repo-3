import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Pressable,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, spacing } from '@/src/theme';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { useAuth } from '@/src/auth-context';

export default function SignUp() {
  const router = useRouter();
  const { signUp } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [homeCourse, setHomeCourse] = useState('');
  const [handicap, setHandicap] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async () => {
    setErr(null);
    if (!email.trim() || !password || !displayName.trim()) {
      setErr('Email, password, and display name are required');
      return;
    }
    if (password.length < 6) {
      setErr('Password must be at least 6 characters');
      return;
    }
    setLoading(true);
    try {
      await signUp({
        email: email.trim(),
        password,
        display_name: displayName.trim(),
        home_course: homeCourse.trim() || undefined,
        handicap: handicap ? Number(handicap) : undefined,
      });
    } catch (e: any) {
      setErr(e?.message || 'Sign up failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container} testID="sign-up-screen">
      <View style={styles.topBar}>
        <Pressable
          testID="sign-up-back"
          onPress={() => router.back()}
          hitSlop={12}
          style={styles.backBtn}
        >
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Join TeeBox</Text>
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={styles.form} keyboardShouldPersistTaps="handled">
          <Text style={styles.subtitle}>Build your golf identity in 30 seconds.</Text>
          <TBInput
            label="Display name"
            testID="sign-up-name"
            value={displayName}
            onChangeText={setDisplayName}
            placeholder="Jordan Kim"
          />
          <TBInput
            label="Email"
            testID="sign-up-email"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            placeholder="you@teebox.com"
          />
          <TBInput
            label="Password"
            testID="sign-up-password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholder="At least 6 characters"
          />
          <TBInput
            label="Home course (optional)"
            testID="sign-up-home-course"
            value={homeCourse}
            onChangeText={setHomeCourse}
            placeholder="Pebble Meadows GC"
          />
          <TBInput
            label="Handicap index (optional)"
            testID="sign-up-handicap"
            value={handicap}
            onChangeText={setHandicap}
            keyboardType="decimal-pad"
            placeholder="e.g. 12.4"
          />
          {err ? <Text style={styles.errText}>{err}</Text> : null}
          <TBButton
            label="Create account"
            testID="sign-up-submit"
            loading={loading}
            onPress={onSubmit}
            style={{ marginTop: spacing.md }}
          />
          <Pressable
            testID="sign-up-go-signin"
            onPress={() => router.replace('/(auth)/sign-in')}
            style={{ marginTop: spacing.lg, alignSelf: 'center' }}
          >
            <Text style={styles.linkText}>
              Already have an account? <Text style={styles.linkStrong}>Sign in</Text>
            </Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  topBar: {
    paddingTop: 56,
    paddingHorizontal: spacing.xl,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingBottom: spacing.md,
  },
  backBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  title: { fontSize: 24, fontWeight: '800', color: colors.onSurface },
  form: { padding: spacing.xl, gap: spacing.md, paddingBottom: spacing.xxxl },
  subtitle: { fontSize: 15, color: colors.muted, marginBottom: spacing.md },
  errText: { color: colors.error, fontWeight: '700', fontSize: 13, marginTop: -4 },
  linkText: { fontSize: 14, color: colors.muted },
  linkStrong: { color: colors.brandPrimary, fontWeight: '800' },
});
