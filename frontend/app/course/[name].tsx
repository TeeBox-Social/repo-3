import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  KeyboardAvoidingView,
  Platform,
  Linking,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { colors, IMAGES, radius, shadow, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { api } from '@/src/api';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';
import { RoundCard } from '@/src/components/RoundCard';
import { StarPicker } from '@/src/components/StarPicker';
import { StarDisplay } from '@/src/components/StarDisplay';
import { WishlistButton } from '@/src/components/WishlistButton';
import { HomeCourseButton } from '@/src/components/HomeCourseButton';
import { CourseFactSheet } from '@/src/components/CourseFactSheet';

type Filter = 'all' | 'low' | 'mid' | 'high';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'low', label: 'Low HC (<10)' },
  { key: 'mid', label: 'Mid HC 10–20' },
  { key: 'high', label: 'High HC 20+' },
];

function inBucket(hc: number | null | undefined, f: Filter): boolean {
  if (f === 'all') return true;
  if (hc == null) return false; // no-HC only in All
  if (f === 'low') return hc < 10;
  if (f === 'mid') return hc >= 10 && hc <= 20;
  if (f === 'high') return hc > 20;
  return true;
}

export default function CourseDetail() {
  useTheme();
  const { name } = useLocalSearchParams<{ name: string }>();
  const router = useRouter();
  const courseName = decodeURIComponent(String(name || ''));
  const [info, setInfo] = useState<any>(null);
  const [reviews, setReviews] = useState<any[] | null>(null);
  const [rounds, setRounds] = useState<any[] | null>(null);
  const [text, setText] = useState('');
  const [rating, setRating] = useState(4.0);
  const [filter, setFilter] = useState<Filter>('all');
  const [posting, setPosting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [i, rvs, rds] = await Promise.all([
        api.courseInfo(courseName),
        api.courseReviews(courseName),
        api.courseRounds(courseName),
      ]);
      setInfo(i);
      setReviews(rvs);
      setRounds(rds);
    } catch {}
  }, [courseName]);

  useEffect(() => {
    load();
  }, [load]);

  const avgRating: number | null = info?.avg_rating ?? null;

  const filteredReviews = useMemo(() => {
    if (!reviews) return [];
    return reviews.filter((r) => inBucket(r.author?.handicap, filter));
  }, [reviews, filter]);

  const submit = async () => {
    setErr(null);
    if (!text.trim()) {
      setErr('Write a quick review');
      return;
    }
    setPosting(true);
    try {
      await api.createReview({ course_name: courseName, rating, text: text.trim() });
      setText('');
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      await load();
    } catch (e: any) {
      setErr(e?.message || 'Failed to post');
    } finally {
      setPosting(false);
    }
  };

  const openMaps = () => {
    const query = encodeURIComponent(
      [courseName, info?.city, info?.region].filter(Boolean).join(' '),
    );
    const url = `https://www.google.com/maps/search/?api=1&query=${query}`;
    Linking.openURL(url).catch(() => {});
  };

  const onLike = async (rid: string) => {
    if (!rounds) return;
    setRounds(
      rounds.map((r) =>
        r.id === rid
          ? {
              ...r,
              liked_by_me: !r.liked_by_me,
              like_count: r.liked_by_me ? Math.max(0, r.like_count - 1) : r.like_count + 1,
            }
          : r,
      ),
    );
    try {
      const res = await api.toggleLike(rid);
      setRounds((prev) =>
        prev
          ? prev.map((r) =>
              r.id === rid ? { ...r, liked_by_me: res.liked, like_count: res.like_count } : r,
            )
          : prev,
      );
    } catch {}
  };

  const locationLabel = [info?.city, info?.region, info?.country].filter(Boolean).join(', ');

  return (
    <View style={styles.container} testID="course-detail-screen">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={{ paddingBottom: 60 }} showsVerticalScrollIndicator={false}>
          <View style={styles.hero}>
            <Image source={{ uri: IMAGES.courseThumb }} style={StyleSheet.absoluteFillObject} contentFit="cover" />
            <LinearGradient
              colors={['rgba(19,42,28,0.2)', 'rgba(19,42,28,0.9)']}
              style={StyleSheet.absoluteFillObject}
            />
            <SafeAreaView edges={['top']} style={styles.heroTop}>
              <Pressable testID="course-back" onPress={() => router.back()} style={styles.iconBtn} hitSlop={8}>
                <Ionicons name="chevron-back" size={22} color="#fff" />
              </Pressable>
            </SafeAreaView>
            <View style={styles.heroCopy}>
              <Text style={styles.heroName}>{courseName}</Text>
              <View style={styles.heroMetaRow}>
                {avgRating != null ? (
                  <View style={styles.avgPill} testID="course-avg-pill">
                    <Ionicons name="star" size={13} color="#F5D442" />
                    <Text style={styles.avgPillText}>
                      {avgRating.toFixed(2)}
                    </Text>
                    <Text style={styles.avgPillSub}> · {reviews?.length ?? 0} reviews</Text>
                  </View>
                ) : (
                  <View style={styles.avgPill}>
                    <Ionicons name="star-outline" size={13} color="#DCFCE7" />
                    <Text style={styles.avgPillSub}>Be the first to review</Text>
                  </View>
                )}
                {locationLabel ? (
                  <View style={styles.locPill}>
                    <Ionicons name="location-outline" size={13} color="#DCFCE7" />
                    <Text style={styles.locText}>{locationLabel}</Text>
                  </View>
                ) : null}
                {info?.par ? (
                  <View style={styles.locPill}>
                    <Ionicons name="golf-outline" size={13} color="#DCFCE7" />
                    <Text style={styles.locText}>
                      Par {info.par}
                      {info?.total_yardage ? ` · ${info.total_yardage} yds` : ''}
                      {info?.course_type ? ` · ${info.course_type}` : ''}
                    </Text>
                  </View>
                ) : null}
              </View>
              <View style={styles.actionsRow}>
                <Pressable
                  testID="course-open-maps"
                  onPress={openMaps}
                  style={styles.mapsPill}
                >
                  <Ionicons name="map" size={15} color={colors.brandDeep} />
                  <Text style={styles.mapsText}>Open in Maps</Text>
                  <Ionicons name="open-outline" size={14} color={colors.brandDeep} />
                </Pressable>
                <WishlistButton courseName={courseName} />
                <HomeCourseButton courseName={courseName} />
              </View>
            </View>
          </View>

          <View style={styles.body}>
            <CourseFactSheet info={info} />

            <Text style={styles.sectionTitle}>Write a review</Text>
            <StarPicker value={rating} onChange={setRating} testID="course-star-picker" />
            <TBInput
              testID="course-review-input"
              value={text}
              onChangeText={setText}
              placeholder="Fairways in great shape, greens rolled fast..."
              multiline
              style={{ minHeight: 80, textAlignVertical: 'top' }}
            />
            {err ? <Text style={styles.errText}>{err}</Text> : null}
            <TBButton
              label={posting ? 'Posting…' : 'Post review'}
              testID="course-review-submit"
              onPress={submit}
              loading={posting}
            />

            <View style={styles.reviewsHeader}>
              <Text style={styles.sectionTitle}>Reviews</Text>
              <Text style={styles.reviewsCount}>
                {filteredReviews.length}
                {reviews && filteredReviews.length !== reviews.length ? ` / ${reviews.length}` : ''}
              </Text>
            </View>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.chipsRow}
            >
              {FILTERS.map((f) => (
                <Pressable
                  key={f.key}
                  testID={`review-filter-${f.key}`}
                  onPress={() => setFilter(f.key)}
                  style={[styles.chip, filter === f.key && styles.chipActive]}
                >
                  <Text style={[styles.chipText, filter === f.key && styles.chipTextActive]}>
                    {f.label}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
            {filteredReviews.length > 0 ? (
              filteredReviews.map((r) => (
                <ReviewCard key={r.id} r={r} courseAvg={avgRating} />
              ))
            ) : (
              <Text style={styles.emptyText}>
                {filter === 'all'
                  ? 'No reviews yet. Yours could be the first.'
                  : 'No reviews match this filter yet.'}
              </Text>
            )}

            <View testID="course-all-rounds" style={{ marginTop: spacing.xl }}>
              <View style={styles.sectionHeaderRow}>
                <Text style={styles.sectionTitle}>All rounds here</Text>
                <View style={styles.allPill}>
                  <Text style={styles.allPillText}>All</Text>
                </View>
              </View>
              {rounds && rounds.length > 0 ? (
                rounds.map((r) => <RoundCard key={r.id} round={r} onLike={() => onLike(r.id)} />)
              ) : (
                <Text style={styles.emptyText}>Be the first golfer to log a round here.</Text>
              )}
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

function ReviewCard({ r, courseAvg }: { r: any; courseAvg: number | null }) {
  const initials = (r.author?.display_name || 'G')
    .split(' ')
    .map((s: string) => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  const hc = r.author?.handicap;
  const diff = courseAvg != null ? r.rating - courseAvg : null;
  const diffTone =
    diff == null ? 'neutral' : diff > 0.1 ? 'up' : diff < -0.1 ? 'down' : 'eq';
  return (
    <View style={styles.reviewCard} testID={`review-${r.id}`}>
      <View style={styles.reviewHeader}>
        <View style={styles.reviewAvatar}>
          {r.author?.avatar ? (
            <Image source={{ uri: r.author.avatar }} style={{ width: '100%', height: '100%' }} />
          ) : (
            <Text style={styles.reviewAvatarText}>{initials}</Text>
          )}
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <View style={styles.reviewNameRow}>
            <Text style={styles.reviewAuthor} numberOfLines={1}>
              {r.author?.display_name || 'Golfer'}
            </Text>
            <View style={styles.ratingBadge}>
              <Ionicons name="star" size={11} color="#fff" />
              <Text style={styles.ratingBadgeText}>{Number(r.rating).toFixed(2)}</Text>
            </View>
            {courseAvg != null ? (
              <View
                style={[
                  styles.avgBadge,
                  diffTone === 'up' && styles.avgBadgeUp,
                  diffTone === 'down' && styles.avgBadgeDown,
                ]}
              >
                <Text style={styles.avgBadgeText}>avg {courseAvg.toFixed(2)}</Text>
              </View>
            ) : null}
          </View>
          <View style={styles.reviewMetaRow}>
            <StarDisplay value={Number(r.rating)} size={13} />
            <Text style={styles.reviewMeta}>
              {hc != null ? `HC ${hc}` : 'no HC'}
            </Text>
          </View>
        </View>
      </View>
      <Text style={styles.reviewText}>{r.text}</Text>
    </View>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  hero: { minHeight: 260 },
  heroTop: { paddingHorizontal: spacing.lg },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(0,0,0,0.35)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  heroCopy: {
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.xl,
    paddingTop: spacing.xxxl,
    gap: spacing.sm,
  },
  heroName: { color: '#fff', fontSize: 28, fontWeight: '800' },
  heroMetaRow: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  avgPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(255,255,255,0.16)',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: radius.pill,
  },
  avgPillText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  avgPillSub: { color: '#DCFCE7', fontSize: 12, fontWeight: '600' },
  locPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(255,255,255,0.16)',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: radius.pill,
  },
  locText: { color: '#DCFCE7', fontSize: 12, fontWeight: '600' },
  mapsPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
    marginTop: spacing.xs,
    ...shadow.soft,
  },
  mapsText: { color: colors.brandDeep, fontWeight: '800', fontSize: 13 },
  actionsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xs },
  body: { padding: spacing.xl, gap: spacing.md },
  sectionTitle: { fontSize: 18, fontWeight: '800', color: colors.onSurface },
  sectionHeaderRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md },
  allPill: {
    backgroundColor: colors.brandTertiary,
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  allPillText: { fontSize: 11, fontWeight: '800', color: colors.onBrandTertiary, letterSpacing: 0.5 },
  errText: { color: colors.error, fontWeight: '700', fontSize: 13 },
  emptyText: { color: colors.muted, fontSize: 14, fontStyle: 'italic' },
  reviewsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.xl,
  },
  reviewsCount: {
    fontSize: 12,
    fontWeight: '800',
    color: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  chipsRow: { gap: spacing.sm, paddingRight: spacing.xl, paddingBottom: spacing.sm },
  chip: {
    height: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  chipActive: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  chipText: { fontWeight: '800', fontSize: 12, color: colors.onSurface },
  chipTextActive: { color: '#fff' },
  reviewCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.sm,
    marginBottom: spacing.sm,
    ...shadow.soft,
  },
  reviewHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  reviewAvatar: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  reviewAvatarText: { color: colors.onBrandTertiary, fontWeight: '800', fontSize: 13 },
  reviewNameRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  reviewAuthor: { fontSize: 14, fontWeight: '800', color: colors.onSurface },
  ratingBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  ratingBadgeText: { color: '#fff', fontSize: 11, fontWeight: '800' },
  avgBadge: {
    backgroundColor: colors.surfaceTertiary,
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  avgBadgeUp: { backgroundColor: '#D6F1DE' },
  avgBadgeDown: { backgroundColor: '#F6E3D9' },
  avgBadgeText: { fontSize: 11, fontWeight: '700', color: colors.onSurfaceTertiary },
  reviewMetaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: 4 },
  reviewMeta: { fontSize: 11, color: colors.muted, fontWeight: '700', letterSpacing: 0.4 },
  reviewText: { fontSize: 14, color: colors.onSurface, lineHeight: 20 },
}));
