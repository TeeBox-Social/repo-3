import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, spacing } from '@/src/theme';
import { TBButton } from '@/src/components/TBButton';
import { api } from '@/src/api';

type Status = 'loading' | 'success' | 'error' | 'missing';

export default function VerifyEmail() {
  const router = useRouter();
  const params = useLocalSearchParams<{ token?: string }>();
  const token = typeof params.token === 'string' ? params.token : '';
  const [status, setStatus] = useState<Status>('loading');
  const [msg, setMsg] = useState<string>('');

  useEffect(() => {
    if (!token) {
      setStatus('missing');
      return;
    }
    (async () => {
      try {
        const res = await api.verifyEmail(token);
        setMsg(res.message || 'Email verified.');
        setStatus('success');
      } catch (e: any) {
        setMsg(e?.message || 'Verification link is invalid or expired.');
        setStatus('error');
      }
    })();
  }, [token]);

  const iconName =
    status === 'success' ? 'checkmark-circle' : status === 'loading' ? 'mail-outline' : 'alert-circle';

  return (
    <SafeAreaView style={styles.container} testID="verify-email-screen">
      <View style={styles.body}>
        <View style={styles.iconWrap}>
          {status === 'loading' ? (
            <ActivityIndicator color={colors.brandPrimary} size="large" />
          ) : (
            <Ionicons name={iconName as any} size={44} color={colors.brandPrimary} />
          )}
        </View>
        <Text style={styles.title}>
          {status === 'success'
            ? 'You\u2019re verified!'
            : status === 'loading'
              ? 'Verifying your email\u2026'
              : status === 'missing'
                ? 'No token provided'
                : 'Verification failed'}
        </Text>
        <Text style={styles.sub}>
          {status === 'success'
            ? msg
            : status === 'loading'
              ? 'Hang tight — we\u2019re confirming your email address with the server.'
              : status === 'missing'
                ? 'Open this page from the verify link in your inbox.'
                : msg}
        </Text>
        {status !== 'loading' ? (
          <TBButton
            label={status === 'success' ? 'Continue to TeeBox' : 'Back to sign in'}
            testID="verify-continue"
            onPress={() => router.replace('/(auth)/sign-in' as any)}
            style={{ marginTop: spacing.xl }}
          />
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  body: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing.xl },
  iconWrap: {
    width: 88,
    height: 88,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  title: { fontSize: 26, fontWeight: '800', color: colors.onSurface, textAlign: 'center' },
  sub: { fontSize: 14, color: colors.muted, textAlign: 'center', lineHeight: 20, marginTop: spacing.sm },
});
