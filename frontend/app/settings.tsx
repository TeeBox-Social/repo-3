import React from 'react';
import { ScrollView, StyleSheet, Text, View, Pressable, Image, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { useAuth } from '@/src/auth-context';

type Appearance = 'light' | 'dark' | 'system';
const OPTIONS: { value: Appearance; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { value: 'light', label: 'Light', icon: 'sunny-outline' },
  { value: 'dark', label: 'Dark', icon: 'moon-outline' },
  { value: 'system', label: 'System', icon: 'phone-portrait-outline' },
];

export default function SettingsScreen() {
  const { preference, setPreference } = useTheme();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const appearance = preference;

  const chooseAppearance = (value: Appearance) => {
    setPreference(value);
  };

  const confirmLogout = () => {
    Alert.alert('Log out', 'Are you sure you want to log out?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Log out',
        style: 'destructive',
        onPress: async () => {
          await signOut();
          router.replace('/(auth)/sign-in');
        },
      },
    ]);
  };

  const initial = (user?.display_name || '?').charAt(0).toUpperCase();
  const version = Constants.expoConfig?.version ?? '1.0.0';

  return (
    <SafeAreaView edges={['top']} style={styles.container}>
      <View style={styles.header}>
        <Pressable testID="settings-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Settings</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        testID="settings-screen"
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.xl }}
        showsVerticalScrollIndicator={false}
      >
        {/* Account */}
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>Account</Text>
          <View style={styles.card}>
            <View style={styles.accountRow}>
              {user?.avatar ? (
                <Image source={{ uri: user.avatar }} style={styles.avatar} />
              ) : (
                <View style={[styles.avatar, styles.avatarFallback]}>
                  <Text style={styles.avatarInitial}>{initial}</Text>
                </View>
              )}
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{user?.display_name ?? 'Golfer'}</Text>
                <View style={styles.emailRow}>
                  <Text style={styles.email} numberOfLines={1}>
                    {user?.email ?? '—'}
                  </Text>
                  {user?.email_verified ? (
                    <View style={styles.verified}>
                      <Ionicons name="checkmark-circle" size={13} color={colors.success} />
                      <Text style={styles.verifiedText}>Verified</Text>
                    </View>
                  ) : null}
                </View>
              </View>
            </View>
            <Pressable
              testID="settings-edit-profile"
              onPress={() => router.push('/profile/edit')}
              style={({ pressed }) => [styles.linkRow, pressed && { opacity: 0.85 }]}
            >
              <Ionicons name="create-outline" size={19} color={colors.onSurface} />
              <Text style={styles.linkText}>Edit profile</Text>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          </View>
        </View>

        {/* Appearance */}
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>Appearance</Text>
          <View style={styles.card}>
            <View style={styles.segment}>
              {OPTIONS.map((opt) => {
                const active = appearance === opt.value;
                return (
                  <Pressable
                    key={opt.value}
                    testID={`settings-appearance-${opt.value}`}
                    onPress={() => chooseAppearance(opt.value)}
                    style={[styles.segmentItem, active && styles.segmentItemActive]}
                  >
                    <Ionicons name={opt.icon} size={18} color={active ? colors.onBrandPrimary : colors.onSurface} />
                    <Text style={[styles.segmentText, active && { color: colors.onBrandPrimary }]}>{opt.label}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={styles.caption}>
              Switch between Light, Dark, or match your device with System.
            </Text>
          </View>
        </View>

        {/* About */}
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>About</Text>
          <View style={styles.card}>
            <View style={styles.aboutRow}>
              <Text style={styles.aboutKey}>Version</Text>
              <Text style={styles.aboutVal}>{version}</Text>
            </View>
          </View>
        </View>

        <Pressable testID="settings-logout" onPress={confirmLogout} style={({ pressed }) => [styles.logout, pressed && { opacity: 0.85 }]}>
          <Ionicons name="log-out-outline" size={20} color={colors.error} />
          <Text style={styles.logoutText}>Log out</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 18, fontWeight: '800', color: colors.onSurface },
  section: { gap: spacing.sm },
  sectionLabel: { fontSize: 12, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5, marginLeft: spacing.xs },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, ...shadow.card },
  accountRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  avatar: { width: 56, height: 56, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary },
  avatarFallback: { alignItems: 'center', justifyContent: 'center', backgroundColor: colors.brandTertiary },
  avatarInitial: { fontSize: 22, fontWeight: '800', color: colors.brandDeep },
  name: { fontSize: 17, fontWeight: '800', color: colors.onSurface },
  emailRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: 2 },
  email: { fontSize: 13, color: colors.muted, flexShrink: 1 },
  verified: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  verifiedText: { fontSize: 11, fontWeight: '700', color: colors.success },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  linkText: { flex: 1, fontSize: 15, fontWeight: '700', color: colors.onSurface },
  segment: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    padding: 4,
    gap: 4,
  },
  segmentItem: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    borderRadius: radius.sm,
  },
  segmentItemActive: { backgroundColor: colors.brandPrimary },
  segmentText: { fontSize: 13.5, fontWeight: '700', color: colors.onSurface },
  caption: { fontSize: 12, color: colors.muted, lineHeight: 17 },
  aboutRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  aboutKey: { fontSize: 14, fontWeight: '700', color: colors.onSurface },
  aboutVal: { fontSize: 14, color: colors.muted },
  logout: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
  },
  logoutText: { fontSize: 15, fontWeight: '800', color: colors.error },
}));
