import React from 'react';
import { ScrollView, StyleSheet, Text, View, Pressable, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { useAuth } from '@/src/auth-context';

type RowProps = {
  icon: keyof typeof Ionicons.glyphMap;
  iconBg: string;
  iconColor: string;
  title: string;
  subtitle: string;
  onPress: () => void;
  testID?: string;
  highlight?: boolean;
};

function MenuRow({ icon, iconBg, iconColor, title, subtitle, onPress, testID, highlight }: RowProps) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [styles.row, highlight && styles.rowHighlight, pressed && { opacity: 0.85 }]}
    >
      <View style={[styles.rowIcon, { backgroundColor: iconBg }]}>
        <Ionicons name={icon} size={20} color={iconColor} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[styles.rowTitle, highlight && { color: colors.brandDeep }]}>{title}</Text>
        <Text style={styles.rowSub}>{subtitle}</Text>
      </View>
      <Ionicons name="chevron-forward" size={20} color={colors.muted} />
    </Pressable>
  );
}

export default function MoreScreen() {
  useTheme();
  const router = useRouter();
  const { user, signOut } = useAuth();

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

  return (
    <SafeAreaView edges={['top']} style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>More</Text>
      </View>

      <ScrollView
        testID="more-screen"
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        showsVerticalScrollIndicator={false}
      >
        <MenuRow
          testID="more-profile"
          icon="person-circle-outline"
          iconBg={colors.brandTertiary}
          iconColor={colors.brandDeep}
          title="View profile"
          subtitle={user?.display_name ? `Signed in as ${user.display_name}` : 'Your rounds, stats & wishlist'}
          onPress={() => router.push('/(tabs)/profile')}
        />

        <MenuRow
          testID="more-premium"
          icon="star"
          iconBg="#FEF3C7"
          iconColor={colors.brandSecondary}
          title="Buy Premium"
          subtitle="Unlock ad-free play & advanced stats"
          onPress={() => router.push('/premium')}
          highlight
        />

        <MenuRow
          testID="more-settings"
          icon="settings-outline"
          iconBg={colors.surfaceTertiary}
          iconColor={colors.onSurface}
          title="App Settings"
          subtitle="Account info & appearance"
          onPress={() => router.push('/settings')}
        />

        <MenuRow
          testID="more-notifications"
          icon="notifications-outline"
          iconBg={colors.surfaceTertiary}
          iconColor={colors.onSurface}
          title="Notification settings"
          subtitle="Choose which alerts you receive"
          onPress={() => router.push('/profile/notifications' as any)}
        />

        {user?.is_admin ? (
          <MenuRow
            testID="more-admin"
            icon="construct-outline"
            iconBg={colors.brandTertiary}
            iconColor={colors.brandDeep}
            title="Course Library"
            subtitle="Bulk-import courses from OpenStreetMap"
            onPress={() => router.push('/profile/admin/courses')}
          />
        ) : null}

        <Pressable testID="more-logout" onPress={confirmLogout} style={({ pressed }) => [styles.logout, pressed && { opacity: 0.85 }]}>
          <Ionicons name="log-out-outline" size={20} color={colors.error} />
          <Text style={styles.logoutText}>Log out</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: spacing.sm },
  headerTitle: { fontSize: 30, fontWeight: '800', color: colors.onSurface },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    ...shadow.card,
  },
  rowHighlight: { borderWidth: 1.5, borderColor: '#FDE68A' },
  rowIcon: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowTitle: { fontSize: 16, fontWeight: '800', color: colors.onSurface },
  rowSub: { fontSize: 12.5, color: colors.muted, marginTop: 2 },
  logout: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.lg,
    marginTop: spacing.sm,
  },
  logoutText: { fontSize: 15, fontWeight: '800', color: colors.error },
}));
