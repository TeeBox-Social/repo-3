import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { api } from '@/src/api';

type Row = {
  course_name: string;
  play_count: number;
  best_score: number | null;
  avg_score: number | null;
  last_played: string | null;
  city?: string | null;
  region?: string | null;
  country?: string | null;
};

export default function CoursesPlayed() {
  useTheme();
  const router = useRouter();
  const { userId } = useLocalSearchParams<{ userId: string }>();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      const res = await api.getUserCoursesPlayed(String(userId));
      setRows(res as Row[]);
    } catch {
      setRows([]);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  return (
    <SafeAreaView edges={['top']} style={styles.container} testID="courses-played-screen">
      <View style={styles.header}>
        <Pressable
          testID="courses-played-back"
          onPress={() => router.back()}
          hitSlop={12}
          style={styles.backBtn}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Courses Played</Text>
        <View style={{ width: 40 }} />
      </View>

      {rows === null ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.brandPrimary} />
        </View>
      ) : rows.length === 0 ? (
        <View style={styles.center}>
          <Ionicons name="golf-outline" size={40} color={colors.muted} />
          <Text style={styles.emptyTitle}>No rounds yet</Text>
          <Text style={styles.emptySub}>
            Once this golfer logs a round, the courses will show up here.
          </Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.body}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
        >
          <Text style={styles.count}>{rows.length} unique courses</Text>
          {rows.map((r) => (
            <Pressable
              key={r.course_name}
              testID={`course-row-${r.course_name}`}
              onPress={() =>
                router.push(`/course/${encodeURIComponent(r.course_name)}` as any)
              }
              style={styles.row}
            >
              <View style={styles.rowIcon}>
                <Ionicons name="golf" size={20} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.name} numberOfLines={1}>
                  {r.course_name}
                </Text>
                <Text style={styles.meta} numberOfLines={1}>
                  {r.play_count} {r.play_count === 1 ? 'round' : 'rounds'}
                  {r.best_score != null ? ` · Best ${r.best_score}` : ''}
                  {r.avg_score != null ? ` · Avg ${r.avg_score}` : ''}
                </Text>
                {r.city || r.region ? (
                  <Text style={styles.location} numberOfLines={1}>
                    {[r.city, r.region, r.country].filter(Boolean).join(', ')}
                  </Text>
                ) : null}
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
  },
  backBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: colors.onSurface },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: 6 },
  emptyTitle: { fontSize: 16, fontWeight: '800', color: colors.onSurface, marginTop: spacing.md },
  emptySub: { fontSize: 13, color: colors.muted, textAlign: 'center', lineHeight: 18 },
  body: { padding: spacing.lg, gap: spacing.sm, paddingBottom: spacing.xl * 2 },
  count: {
    fontSize: 12,
    fontWeight: '800',
    color: colors.muted,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    marginBottom: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    ...shadow.soft,
  },
  rowIcon: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  name: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  meta: { fontSize: 12, color: colors.muted, marginTop: 2 },
  location: { fontSize: 11, color: colors.muted, marginTop: 1 },
}));
