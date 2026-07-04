import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  FlatList,
  Pressable,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, IMAGES, radius, shadow, spacing } from '@/src/theme';
import { api } from '@/src/api';

type Tab = 'golfers' | 'courses';

export default function Discover() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>('golfers');
  const [q, setQ] = useState('');
  const [users, setUsers] = useState<any[] | null>(null);
  const [courses, setCourses] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === 'golfers') {
        setUsers(await api.discoverUsers(q));
      } else {
        setCourses(await api.discoverCourses(q));
      }
    } catch {
    } finally {
      setLoading(false);
    }
  }, [tab, q]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  return (
    <View style={styles.container} testID="discover-screen">
      <SafeAreaView edges={['top']} style={styles.headerSafe}>
        <View style={styles.header}>
          <Text style={styles.title}>Discover</Text>
          <View style={styles.searchBox}>
            <Ionicons name="search" size={18} color={colors.muted} />
            <TextInput
              testID="discover-search"
              value={q}
              onChangeText={setQ}
              placeholder={tab === 'golfers' ? 'Search golfers…' : 'Search courses…'}
              placeholderTextColor={colors.muted}
              style={styles.searchInput}
              returnKeyType="search"
            />
            {q ? (
              <Pressable onPress={() => setQ('')} hitSlop={8}>
                <Ionicons name="close-circle" size={18} color={colors.muted} />
              </Pressable>
            ) : null}
          </View>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chipsRow}
          >
            {(['golfers', 'courses'] as Tab[]).map((t) => (
              <Pressable
                key={t}
                testID={`discover-tab-${t}`}
                onPress={() => setTab(t)}
                style={[styles.chip, tab === t && styles.chipActive]}
              >
                <Text style={[styles.chipText, tab === t && styles.chipTextActive]}>
                  {t === 'golfers' ? 'Golfers' : 'Courses'}
                </Text>
              </Pressable>
            ))}
          </ScrollView>
        </View>
      </SafeAreaView>

      {tab === 'golfers' ? (
        <FlatList
          data={users || []}
          keyExtractor={(u) => u.id}
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => <UserRow user={item} onPress={() => router.push(`/user/${item.id}`)} />}
          ListEmptyComponent={loading ? <Spinner /> : <EmptyState label="No golfers found" />}
        />
      ) : (
        <FlatList
          data={courses || []}
          keyExtractor={(c) => c.course_name}
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => (
            <CourseRow
              course={item}
              onPress={() => router.push(`/course/${encodeURIComponent(item.course_name)}`)}
            />
          )}
          ListEmptyComponent={loading ? <Spinner /> : <EmptyState label="No courses yet" />}
        />
      )}
    </View>
  );
}

function Spinner() {
  return (
    <View style={{ paddingVertical: 40, alignItems: 'center' }}>
      <ActivityIndicator color={colors.brandPrimary} />
    </View>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <View style={{ padding: spacing.xxl, alignItems: 'center' }}>
      <Text style={{ color: colors.muted, fontSize: 14 }}>{label}</Text>
    </View>
  );
}

function UserRow({ user, onPress }: { user: any; onPress: () => void }) {
  const initials = (user.display_name || 'G')
    .split(' ')
    .map((s: string) => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  return (
    <Pressable testID={`discover-user-${user.id}`} onPress={onPress} style={styles.row}>
      <View style={styles.avatar}>
        {user.avatar ? (
          <Image source={{ uri: user.avatar }} style={{ width: '100%', height: '100%' }} />
        ) : (
          <Text style={styles.avatarText}>{initials}</Text>
        )}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.rowTitle}>{user.display_name}</Text>
        <Text style={styles.rowSub}>
          {user.home_course ? `${user.home_course} · ` : ''}
          {user.handicap != null ? `HC ${user.handicap}` : 'No handicap yet'}
        </Text>
      </View>
      <View style={styles.rowStat}>
        <Text style={styles.rowStatNum}>{user.round_count || 0}</Text>
        <Text style={styles.rowStatLabel}>rounds</Text>
      </View>
    </Pressable>
  );
}

function CourseRow({ course, onPress }: { course: any; onPress: () => void }) {
  return (
    <Pressable testID={`discover-course-${course.course_name}`} onPress={onPress} style={styles.courseRow}>
      <Image
        source={{ uri: course.last_photo || IMAGES.courseThumb }}
        style={styles.courseImg}
        contentFit="cover"
      />
      <View style={styles.courseBody}>
        <Text style={styles.rowTitle}>{course.course_name}</Text>
        <Text style={styles.rowSub}>
          {course.play_count} plays
          {course.avg_score != null ? ` · Avg ${course.avg_score}` : ''}
          {course.best_score != null ? ` · Best ${course.best_score}` : ''}
        </Text>
        {course.avg_rating ? (
          <View style={styles.ratingPill}>
            <Ionicons name="star" size={11} color={colors.brandSecondary} />
            <Text style={styles.ratingText}>{course.avg_rating} · {course.review_count} reviews</Text>
          </View>
        ) : null}
      </View>
      <Ionicons name="chevron-forward" size={20} color={colors.muted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  headerSafe: { backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider },
  header: { paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.md },
  title: { fontSize: 26, fontWeight: '800', color: colors.onSurface },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    height: 48,
  },
  searchInput: { flex: 1, fontSize: 15, color: colors.onSurface },
  chipsRow: { gap: spacing.sm, paddingRight: spacing.xl },
  chip: {
    height: 36,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  chipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  chipText: { fontWeight: '800', fontSize: 13, color: colors.onSurface },
  chipTextActive: { color: '#fff' },
  listContent: { padding: spacing.lg, paddingBottom: 140, gap: spacing.md },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    marginBottom: spacing.md,
    ...shadow.soft,
  },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarText: { color: colors.onBrandTertiary, fontWeight: '800', fontSize: 17 },
  rowTitle: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  rowSub: { fontSize: 13, color: colors.muted, marginTop: 2 },
  rowStat: { alignItems: 'center', paddingHorizontal: spacing.sm },
  rowStatNum: { fontSize: 18, fontWeight: '800', color: colors.brandPrimary },
  rowStatLabel: { fontSize: 10, color: colors.muted, fontWeight: '700', letterSpacing: 0.4 },
  courseRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.sm,
    gap: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    marginBottom: spacing.md,
    ...shadow.soft,
  },
  courseImg: { width: 70, height: 70, borderRadius: radius.md, backgroundColor: colors.brandTertiary },
  courseBody: { flex: 1, gap: 2 },
  ratingPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.pill,
    paddingHorizontal: 8,
    paddingVertical: 3,
    alignSelf: 'flex-start',
    marginTop: 4,
  },
  ratingText: { fontSize: 11, fontWeight: '700', color: colors.onSurfaceTertiary },
});
