import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, KeyboardAvoidingView, ScrollView, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { api } from '@/src/api';

export default function ForgotPassword() {
  useTheme();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    if (!email.trim()) {
      setErr('Enter the email you registered with.');
      return;
    }
    setLoading(true);
    try {
      await api.requestPasswordReset(email.trim().toLowerCase());
      setDone(true);
    } catch (e: any) {
      const msg = e?.message || 'Something went wrong. Please try again.';
      setErr(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Pressable
          testID="forgot-back"
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
          testID="forgot-screen"
          contentContainerStyle={styles.body}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.iconWrap}>
            <Ionicons name={done ? 'checkmark-done' : 'lock-open-outline'} size={32} color={colors.brandPrimary} />
          </View>
          <Text style={styles.title}>{done ? 'Check your inbox' : 'Reset your password'}</Text>
          <Text style={styles.sub}>
            {done
              ? "If that email is registered, we've just sent a reset link. It expires in 30 minutes."
              : 'Enter your account email and we\u2019ll send you a link to set a new password. Successful reset also unlocks a locked account.'}
          </Text>

          {!done ? (
            <>
              <TBInput
                label="Email"
                testID="forgot-email"
                value={email}
                onChangeText={setEmail}
                autoCapitalize="none"
                autoComplete="email"
                keyboardType="email-address"
                placeholder="you@teebox.com"
              />
              {err ? <Text style={styles.err} testID="forgot-error">{err}</Text> : null}
              <TBButton
                label="Send reset link"
                testID="forgot-submit"
                loading={loading}
                onPress={submit}
                style={{ marginTop: spacing.md }}
              />
            </>
          ) : (
            <TBButton
              label="Back to sign in"
              testID="forgot-back-to-signin"
              onPress={() => router.replace('/(auth)/sign-in' as any)}
              style={{ marginTop: spacing.lg }}
            />
          )}
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
}));
