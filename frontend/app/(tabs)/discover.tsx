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
  Linking,
} from 'react-native';
import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import { colors, IMAGES, radius, shadow, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { api } from '@/src/api';
import { NotificationBell } from '@/src/components/NotificationBell';

type Tab = 'golfers' | 'courses';
type LocationState =
  | { status: 'idle' }
  | { status: 'requesting' }
  | { status: 'denied'; canAskAgain: boolean }
  | { status: 'granted'; coords: { lat: number; lng: number } }
  | { status: 'error' };

export default function Discover() {
  useTheme();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>('courses');
  const [q, setQ] = useState('');
  const [users, setUsers] = useState<any[] | null>(null);
  const [courses, setCourses] = useState<any[] | null>(null);
  const [nearby, setNearby] = useState<any[] | null>(null);
  const [nearbyLoading, setNearbyLoading] = useState(false);
  const [loc, setLoc] = useState<LocationState>({ status: 'idle' });
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

  const fetchNearby = useCallback(async () => {
    setNearbyLoading(true);
    try {
      const pos = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      const coords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      setLoc({ status: 'granted', coords });
      const list = await api.discoverCoursesNearby(coords.lat, coords.lng, 80);
      setNearby(list);
    } catch {
      setLoc({ status: 'error' });
      setNearby([]);
    } finally {
      setNearbyLoading(false);
    }
  }, []);

  // Check the current location-permission status (without prompting) once when
  // the Courses tab becomes active. If already granted, we auto-fetch nearby
  // courses so the empty-search state is immediately populated.
  const checkExistingPermission = useCallback(async () => {
    try {
      const { status, canAskAgain } = await Location.getForegroundPermissionsAsync();
      if (status === 'granted') {
        await fetchNearby();
      } else if (status === 'denied') {
        setLoc({ status: 'denied', canAskAgain });
      }
    } catch {
      setLoc({ status: 'error' });
    }
  }, [fetchNearby]);

  useEffect(() => {
    if (tab === 'courses' && !q && loc.status === 'idle') {
      checkExistingPermission();
    }
  }, [tab, q, loc.status, checkExistingPermission]);

  const requestLocation = useCallback(async () => {
    setLoc({ status: 'requesting' });
    try {
      const res = await Location.requestForegroundPermissionsAsync();
      if (res.status === 'granted') {
        await fetchNearby();
      } else {
        setLoc({ status: 'denied', canAskAgain: res.canAskAgain });
      }
    } catch {
      setLoc({ status: 'error' });
    }
  }, [fetchNearby]);

  const openSettings = () => {
    Linking.openSettings().catch(() => {});
  };

  // Show nearby ONLY on Courses tab when the search bar is empty.
  const showNearby = tab === 'courses' && !q.trim();

  return (
    <View style={styles.container} testID="discover-screen">
      <SafeAreaView edges={['top']} style={styles.headerSafe}>
        <View style={styles.header}>
          <View style={styles.titleRow}>
            <Text style={styles.title}>Discover</Text>
            <NotificationBell />
          </View>
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
            {(['courses', 'golfers'] as Tab[]).map((t) => (
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
          data={showNearby ? (nearby || []) : (courses || [])}
          keyExtractor={(c) => c.course_name}
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => (
            <CourseRow
              course={item}
              onPress={() => router.push(`/course/${encodeURIComponent(item.course_name)}`)}
            />
          )}
          ListHeaderComponent={
            showNearby ? (
              <NearbyHeader
                loc={loc}
                loading={nearbyLoading}
                count={nearby?.length ?? 0}
                onEnable={requestLocation}
                onOpenSettings={openSettings}
              />
            ) : null
          }
          ListEmptyComponent={
            loading || nearbyLoading ? (
              <Spinner />
            ) : showNearby && loc.status === 'granted' ? (
              <EmptyState label="No courses within 50 mi — try searching by name." />
            ) : showNearby ? null : (
              <EmptyState label="No courses match your search" />
            )
          }
        />
      )}
    </View>
  );
}

function NearbyHeader({
  loc,
  loading,
  count,
  onEnable,
  onOpenSettings,
}: {
  loc: LocationState;
  loading: boolean;
  count: number;
  onEnable: () => void;
  onOpenSettings: () => void;
}) {
  // Idle / not-yet-asked — invite the user
  if (loc.status === 'idle' || loc.status === 'requesting') {
    return (
      <View style={styles.nearbyCard} testID="discover-nearby-enable">
        <View style={styles.nearbyIcon}>
          <Ionicons name="location" size={22} color={colors.brandPrimary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.nearbyTitle}>Find courses nearby</Text>
          <Text style={styles.nearbySub}>
            Share your location to see the closest tee times. TeeBox never stores your coordinates.
          </Text>
        </View>
        <Pressable
          onPress={onEnable}
          style={styles.nearbyBtn}
          disabled={loc.status === 'requesting'}
          testID="discover-nearby-enable-btn"
        >
          <Text style={styles.nearbyBtnText}>
            {loc.status === 'requesting' ? 'Locating…' : 'Enable'}
          </Text>
        </Pressable>
      </View>
    );
  }

  if (loc.status === 'denied') {
    return (
      <View style={styles.nearbyCard} testID="discover-nearby-denied">
        <View style={[styles.nearbyIcon, { backgroundColor: colors.surfaceTertiary }]}>
          <Ionicons name="location-outline" size={22} color={colors.muted} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.nearbyTitle}>Location off</Text>
          <Text style={styles.nearbySub}>
            {loc.canAskAgain
              ? 'Enable location to see courses near you.'
              : 'Turn on location in Settings to see nearby courses.'}
          </Text>
        </View>
        <Pressable
          onPress={loc.canAskAgain ? onEnable : onOpenSettings}
          style={styles.nearbyBtn}
          testID="discover-nearby-settings-btn"
        >
          <Text style={styles.nearbyBtnText}>
            {loc.canAskAgain ? 'Enable' : 'Open Settings'}
          </Text>
        </Pressable>
      </View>
    );
  }

  if (loc.status === 'error') {
    return (
      <View style={styles.nearbyCard}>
        <View style={[styles.nearbyIcon, { backgroundColor: colors.surfaceTertiary }]}>
          <Ionicons name="warning-outline" size={22} color={colors.muted} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.nearbyTitle}>Couldn&apos;t get your location</Text>
          <Text style={styles.nearbySub}>Try again in a moment.</Text>
        </View>
        <Pressable onPress={onEnable} style={styles.nearbyBtn}>
          <Text style={styles.nearbyBtnText}>Retry</Text>
        </Pressable>
      </View>
    );
  }

  // granted
  return (
    <View style={styles.nearbyBanner} testID="discover-nearby-header">
      <Ionicons name="navigate" size={14} color={colors.brandPrimary} />
      <Text style={styles.nearbyBannerText}>
        {loading ? 'Finding nearby courses…' : `${count} course${count === 1 ? '' : 's'} within 50 mi`}
      </Text>
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
  const location = [course.city, course.region].filter(Boolean).join(', ');
  return (
    <Pressable testID={`discover-course-${course.course_name}`} onPress={onPress} style={styles.courseRow}>
      <Image
        source={{ uri: course.last_photo || IMAGES.courseThumb }}
        style={styles.courseImg}
        contentFit="cover"
      />
      <View style={styles.courseBody}>
        <Text style={styles.rowTitle} numberOfLines={1}>{course.course_name}</Text>
        {location ? (
          <View style={styles.locationRow}>
            <Ionicons name="location-outline" size={11} color={colors.muted} />
            <Text style={styles.locationText} numberOfLines={1}>{location}</Text>
          </View>
        ) : null}
        <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
          {typeof course.distance_km === 'number' ? (
            <View style={styles.distancePill}>
              <Ionicons name="navigate" size={10} color={colors.brandPrimary} />
              <Text style={styles.distanceText}>
                {(() => {
                  const mi = course.distance_km * 0.621371;
                  if (mi < 0.1) {
                    // Sub-tenth-mile → show feet for a friendly close-range readout.
                    return `${Math.round(mi * 5280)} ft away`;
                  }
                  return `${mi.toFixed(mi < 10 ? 1 : 0)} mi away`;
                })()}
              </Text>
            </View>
          ) : null}
          {course.source === 'opengolfapi' ? (
            <View style={styles.nationwidePill} testID={`discover-course-nationwide-${course.course_name}`}>
              <Ionicons name="globe-outline" size={10} color={colors.brandSecondary} />
              <Text style={styles.nationwideText}>Nationwide</Text>
            </View>
          ) : null}
        </View>
        <Text style={styles.rowSub} numberOfLines={1}>
          {course.play_count > 0
            ? `${course.play_count} play${course.play_count > 1 ? 's' : ''}`
            : 'Not played yet'}
          {course.avg_score != null ? ` · Avg ${course.avg_score}` : ''}
          {course.best_score != null ? ` · Best ${course.best_score}` : ''}
        </Text>
        {course.avg_rating != null ? (
          <View style={styles.ratingPill}>
            <Ionicons name="star" size={11} color={colors.brandSecondary} />
            <Text style={styles.ratingText}>
              {Number(course.avg_rating).toFixed(2)} · {course.review_count} reviews
            </Text>
          </View>
        ) : null}
      </View>
      <Ionicons name="chevron-forward" size={20} color={colors.muted} />
    </Pressable>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  headerSafe: { backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider },
  header: { paddingHorizontal: spacing.xl, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.md },
  title: { fontSize: 26, fontWeight: '800', color: colors.onSurface },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
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
  locationRow: { flexDirection: 'row', alignItems: 'center', gap: 3, marginTop: 1 },
  locationText: { fontSize: 12, color: colors.muted, fontWeight: '600', flex: 1 },
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
  distancePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.pill,
    paddingHorizontal: 8,
    paddingVertical: 3,
    alignSelf: 'flex-start',
    marginTop: 4,
  },
  distanceText: { fontSize: 11, fontWeight: '800', color: colors.brandPrimary },
  nationwidePill: {
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
  nationwideText: { fontSize: 11, fontWeight: '800', color: colors.brandSecondary },
  nearbyCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadow.soft,
  },
  nearbyIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  nearbyTitle: { fontSize: 14, fontWeight: '800', color: colors.onSurface },
  nearbySub: { fontSize: 12, color: colors.muted, marginTop: 2, lineHeight: 16 },
  nearbyBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  nearbyBtnText: { fontSize: 12, fontWeight: '800', color: '#fff' },
  nearbyBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 4,
    marginBottom: spacing.md,
  },
  nearbyBannerText: { fontSize: 12, fontWeight: '700', color: colors.brandPrimary, letterSpacing: 0.3 },
}));
