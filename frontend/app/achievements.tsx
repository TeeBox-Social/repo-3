import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth-context';

type Achievement = {
  key: string;
  title: string;
  desc: string;
  icon?: string;
  earned: boolean;
};

function iconFor(key?: string): any {
  switch (key) {
    case 'flag':
      return 'flag';
    case 'trophy':
      return 'trophy';
    case 'star':
      return 'star';
    case 'golf':
      return 'golf';
    case 'medal':
      return 'medal';
    case 'map':
      return 'map';
    case 'flame':
      return 'flame';
    default:
      return 'ribbon';
  }
}

export default function AchievementsScreen() {
  useTheme();
  const { user } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<{ total: number; achievements: Achievement[] } | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    try {
      const res = await api.getUserAchievements(user.id);
      setData(res as any);
    } catch {}
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  if (!data) {
    return (
      <View style={styles.center}>
        <Stack.Screen options={{ title: 'Achievements' }} />
        <ActivityIndicator color={colors.brandPrimary} size="large" />
      </View>
    );
  }

  const earned = data.achievements.filter((a) => a.earned);
  const locked = data.achievements.filter((a) => !a.earned);
  const ordered = [...earned, ...locked];
  const progressPct = data.achievements.length
    ? Math.round((data.total / data.achievements.length) * 100)
    : 0;

  return (
    <SafeAreaView edges={['top']} style={styles.container}>
      <Stack.Screen options={{ headerShown: false }} />

      <View style={styles.header}>
        <Pressable
          testID="achievements-back"
          onPress={() => router.back()}
          hitSlop={12}
          style={styles.backBtn}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Achievements</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        testID="achievements-screen"
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingBottom: spacing.xl * 2 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        <View style={styles.progressCard}>
          <View style={{ flex: 1 }}>
            <Text style={styles.progressLabel}>Your progress</Text>
            <Text style={styles.progressCount}>
              {data.total} <Text style={styles.progressCountSlash}>/ {data.achievements.length}</Text>
            </Text>
            <View style={styles.progressBarWrap}>
              <View style={[styles.progressBarFill, { width: `${progressPct}%` }]} />
            </View>
            <Text style={styles.progressPct}>{progressPct}% unlocked</Text>
          </View>
          <View style={styles.progressIcon}>
            <Ionicons name="trophy" size={30} color="#fff" />
          </View>
        </View>

        {earned.length > 0 ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Unlocked · {earned.length}</Text>
            <View style={styles.list}>
              {ordered
                .filter((a) => a.earned)
                .map((a) => (
                  <AchievementRow key={a.key} a={a} />
                ))}
            </View>
          </View>
        ) : (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyTitle}>No achievements unlocked yet</Text>
            <Text style={styles.emptySub}>
              Log a round to start earning badges. Scroll down to see all the ones you can chase.
            </Text>
          </View>
        )}

        {locked.length > 0 ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Locked · {locked.length}</Text>
            <View style={styles.list}>
              {ordered
                .filter((a) => !a.earned)
                .map((a) => (
                  <AchievementRow key={a.key} a={a} />
                ))}
            </View>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function AchievementRow({ a }: { a: Achievement }) {
  return (
    <View
      testID={`achievement-row-${a.key}`}
      style={[styles.row, !a.earned && styles.rowLocked]}
    >
      <View style={[styles.rowIcon, !a.earned && styles.rowIconLocked]}>
        <Ionicons
          name={a.earned ? iconFor(a.icon) : 'lock-closed'}
          size={22}
          color={a.earned ? '#fff' : colors.muted}
        />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[styles.rowTitle, !a.earned && { color: colors.muted }]}>{a.title}</Text>
        <Text style={styles.rowDesc}>{a.desc}</Text>
      </View>
      {a.earned ? (
        <View style={styles.earnedPill}>
          <Ionicons name="checkmark" size={12} color={colors.onBrandTertiary} />
          <Text style={styles.earnedPillText}>Earned</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
    backgroundColor: colors.surface,
  },
  backBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: colors.onSurface },
  progressCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    margin: spacing.lg,
    padding: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    ...shadow.card,
  },
  progressLabel: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    color: colors.muted,
  },
  progressCount: { fontSize: 34, fontWeight: '800', color: colors.brandPrimary, marginTop: 2 },
  progressCountSlash: { fontSize: 18, fontWeight: '700', color: colors.muted },
  progressBarWrap: {
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.surfaceTertiary,
    overflow: 'hidden',
    marginTop: spacing.sm,
  },
  progressBarFill: { height: '100%', backgroundColor: colors.brandPrimary, borderRadius: 4 },
  progressPct: { fontSize: 12, color: colors.muted, marginTop: 6, fontWeight: '600' },
  progressIcon: {
    width: 60,
    height: 60,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadow.soft,
  },
  section: { paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  sectionTitle: {
    fontSize: 12,
    fontWeight: '800',
    color: colors.muted,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    marginBottom: spacing.sm,
  },
  list: { gap: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    ...shadow.soft,
  },
  rowLocked: { backgroundColor: colors.surfaceTertiary, shadowOpacity: 0, elevation: 0 },
  rowIcon: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowIconLocked: {
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  rowTitle: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  rowDesc: { fontSize: 13, color: colors.muted, marginTop: 2, lineHeight: 18 },
  earnedPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
  },
  earnedPillText: { fontSize: 11, fontWeight: '800', color: colors.onBrandTertiary, letterSpacing: 0.4 },
  emptyBox: {
    margin: spacing.lg,
    padding: spacing.xl,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    gap: 6,
  },
  emptyTitle: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  emptySub: { fontSize: 13, color: colors.muted, textAlign: 'center', lineHeight: 18 },
}));
