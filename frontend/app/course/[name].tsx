import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { colors, IMAGES, radius, shadow, spacing } from '@/src/theme';
import { api } from '@/src/api';
import { TBButton } from '@/src/components/TBButton';
import { TBInput } from '@/src/components/TBInput';

export default function CourseDetail() {
  const { name } = useLocalSearchParams<{ name: string }>();
  const router = useRouter();
  const courseName = decodeURIComponent(String(name || ''));
  const [reviews, setReviews] = useState<any[] | null>(null);
  const [text, setText] = useState('');
  const [rating, setRating] = useState(4);
  const [posting, setPosting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setReviews(await api.courseReviews(courseName));
    } catch {}
  }, [courseName]);

  useEffect(() => {
    load();
  }, [load]);

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

  const avg =
    reviews && reviews.length > 0
      ? Math.round((reviews.reduce((s, r) => s + r.rating, 0) / reviews.length) * 10) / 10
      : null;

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
              colors={['rgba(19,42,28,0.2)', 'rgba(19,42,28,0.85)']}
              style={StyleSheet.absoluteFillObject}
            />
            <SafeAreaView edges={['top']} style={styles.heroTop}>
              <Pressable testID="course-back" onPress={() => router.back()} style={styles.iconBtn} hitSlop={8}>
                <Ionicons name="chevron-back" size={22} color="#fff" />
              </Pressable>
            </SafeAreaView>
            <View style={styles.heroCopy}>
              <Text style={styles.heroName}>{courseName}</Text>
              {avg ? (
                <View style={styles.ratingRow}>
                  <Ionicons name="star" size={14} color="#F5D442" />
                  <Text style={styles.ratingText}>
                    {avg} · {reviews?.length} reviews
                  </Text>
                </View>
              ) : (
                <Text style={styles.ratingText}>Be the first to review</Text>
              )}
            </View>
          </View>

          <View style={styles.body}>
            <Text style={styles.sectionTitle}>Write a review</Text>
            <View style={styles.starsRow}>
              {[1, 2, 3, 4, 5].map((s) => (
                <Pressable
                  key={s}
                  testID={`course-star-${s}`}
                  onPress={() => setRating(s)}
                  hitSlop={6}
                >
                  <Ionicons
                    name={s <= rating ? 'star' : 'star-outline'}
                    size={30}
                    color={s <= rating ? colors.brandSecondary : colors.borderStrong}
                  />
                </Pressable>
              ))}
            </View>
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

            <Text style={[styles.sectionTitle, { marginTop: spacing.xl }]}>Reviews</Text>
            {reviews && reviews.length > 0 ? (
              reviews.map((r) => <ReviewCard key={r.id} r={r} />)
            ) : (
              <Text style={styles.emptyText}>No reviews yet. Yours could be the first.</Text>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

function ReviewCard({ r }: { r: any }) {
  const initials = (r.author?.display_name || 'G')
    .split(' ')
    .map((s: string) => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  return (
    <View style={styles.reviewCard}>
      <View style={styles.reviewHeader}>
        <View style={styles.reviewAvatar}>
          {r.author?.avatar ? (
            <Image source={{ uri: r.author.avatar }} style={{ width: '100%', height: '100%' }} />
          ) : (
            <Text style={styles.reviewAvatarText}>{initials}</Text>
          )}
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.reviewAuthor}>{r.author?.display_name || 'Golfer'}</Text>
          <View style={{ flexDirection: 'row', gap: 2, marginTop: 2 }}>
            {[1, 2, 3, 4, 5].map((s) => (
              <Ionicons
                key={s}
                name={s <= r.rating ? 'star' : 'star-outline'}
                size={12}
                color={s <= r.rating ? colors.brandSecondary : colors.borderStrong}
              />
            ))}
          </View>
        </View>
      </View>
      <Text style={styles.reviewText}>{r.text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  hero: { height: 240 },
  heroTop: { paddingHorizontal: spacing.lg },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(0,0,0,0.35)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  heroCopy: { position: 'absolute', left: spacing.xl, right: spacing.xl, bottom: spacing.xl },
  heroName: { color: '#fff', fontSize: 28, fontWeight: '800' },
  ratingRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6 },
  ratingText: { color: '#DCFCE7', fontSize: 14, fontWeight: '600' },
  body: { padding: spacing.xl, gap: spacing.md },
  sectionTitle: { fontSize: 18, fontWeight: '800', color: colors.onSurface },
  starsRow: { flexDirection: 'row', gap: spacing.sm, marginVertical: spacing.sm },
  errText: { color: colors.error, fontWeight: '700', fontSize: 13 },
  emptyText: { color: colors.muted, fontSize: 14, fontStyle: 'italic' },
  reviewCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.sm,
    ...shadow.soft,
  },
  reviewHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  reviewAvatar: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  reviewAvatarText: { color: colors.onBrandTertiary, fontWeight: '800', fontSize: 13 },
  reviewAuthor: { fontSize: 14, fontWeight: '800', color: colors.onSurface },
  reviewText: { fontSize: 14, color: colors.onSurface, lineHeight: 20 },
});
