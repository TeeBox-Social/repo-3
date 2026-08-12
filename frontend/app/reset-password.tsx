import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, Pressable, KeyboardAvoidingView, ScrollView, Platform, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { api } from '@/src/api';

export default function ResetPassword() {
  useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ token?: string }>();
  const token = useMemo(() => (typeof params.token === 'string' ? params.token : ''), [params.token]);
  const [manualToken, setManualToken] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (token && !manualToken) setManualToken(token);
  }, [token, manualToken]);

  const submit = async () => {
    setErr(null);
    const useToken = manualToken.trim();
    if (!useToken) {
      setErr('Missing reset token. Open the link from your email again.');
      return;
    }
    if (password.length < 6) {
      setErr('Password must be at least 6 characters.');
      return;
    }
    if (password !== confirm) {
      setErr('The two passwords do not match.');
      return;
    }
    setLoading(true);
    try {
      await api.resetPassword(useToken, password);
      setDone(true);
    } catch (e: any) {
      setErr(e?.message || 'Could not reset password. The link may be expired.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Pressable
          testID="reset-back"
          onPress={() => router.back()}
          hitSlop={12}
          style={styles.backBtn}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView
          testID="reset-screen"
          contentContainerStyle={styles.body}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.iconWrap}>
            <Ionicons name={done ? 'checkmark-circle' : 'key-outline'} size={32} color={colors.brandPrimary} />
          </View>
          <Text style={styles.title}>{done ? 'Password updated' : 'Set a new password'}</Text>
          <Text style={styles.sub}>
            {done
              ? 'Your password is set and your account is unlocked. Sign in with the new password.'
              : 'Choose a password with at least 6 characters. All existing sessions will be signed out.'}
          </Text>

          {!done ? (
            <>
              {!token ? (
                <TBInput
                  label="Reset token"
                  testID="reset-token"
                  value={manualToken}
                  onChangeText={setManualToken}
                  autoCapitalize="none"
                  placeholder="Paste the token from your email"
                />
              ) : null}
              <TBInput
                label="New password"
                testID="reset-password"
                value={password}
                onChangeText={setPassword}
                autoCapitalize="none"
                secureTextEntry={!show}
                placeholder="At least 6 characters"
                rightAdornment={
                  <Pressable onPress={() => setShow((v) => !v)} hitSlop={10} style={styles.eyeBtn}>
                    <Ionicons name={show ? 'eye-off-outline' : 'eye-outline'} size={20} color={colors.muted} />
                  </Pressable>
                }
              />
              <TBInput
                label="Confirm password"
                testID="reset-confirm"
                value={confirm}
                onChangeText={setConfirm}
                autoCapitalize="none"
                secureTextEntry={!show}
                placeholder="Repeat your new password"
              />
              {err ? <Text style={styles.err} testID="reset-error">{err}</Text> : null}
              <TBButton
                label="Update password"
                testID="reset-submit"
                loading={loading}
                onPress={submit}
                style={{ marginTop: spacing.md }}
              />
            </>
          ) : (
            <TBButton
              label="Sign in"
              testID="reset-go-signin"
              onPress={() => router.replace('/(auth)/sign-in' as any)}
              style={{ marginTop: spacing.lg }}
            />
          )}
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.xxxl, gap: spacing.md },
  iconWrap: {
    width: 64,
    height: 64,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  title: { fontSize: 26, fontWeight: '800', color: colors.onSurface },
  sub: { fontSize: 14, color: colors.muted, lineHeight: 20, marginBottom: spacing.md },
  err: { color: colors.error, fontWeight: '700', fontSize: 13 },
  eyeBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
}));
