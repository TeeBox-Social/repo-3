import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { MentionText } from '@/src/components/MentionText';

type Achievement = {
  key: string;
  title: string;
  desc?: string;
  icon?: string;
};

type Props = {
  round: any;
  onLike: () => void;
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

export function RoundCard({ round, onLike }: Props) {
  const router = useRouter();
  const hasPhoto = round.photos && round.photos.length > 0;
  const scoreDiff = round.total_score - (round.par || 72);
  const scoreLabel = scoreDiff === 0 ? 'E' : scoreDiff > 0 ? `+${scoreDiff}` : `${scoreDiff}`;
  const author = round.author || {};
  const initials = (author.display_name || 'G')
    .split(' ')
    .map((s: string) => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  const openCourse = () => {
    Haptics.selectionAsync().catch(() => {});
    router.push(`/course/${encodeURIComponent(round.course_name)}` as any);
  };

  const openPost = () => {
    Haptics.selectionAsync().catch(() => {});
    router.push(`/post/${round.id}` as any);
  };

  const newAchievements: Achievement[] = Array.isArray(round.new_achievements)
    ? round.new_achievements
    : [];

  return (
    <Pressable testID={`round-card-${round.id}`} style={styles.card} onPress={openPost}>
      {/* Header */}
      <View style={styles.header}>
        <Pressable
          testID={`round-card-author-${round.id}`}
          onPress={() => author.id && router.push(`/user/${author.id}` as any)}
          style={styles.avatar}
        >
          {author.avatar ? (
            <Image source={{ uri: author.avatar }} style={styles.avatarImg} />
          ) : (
            <Text style={styles.avatarText}>{initials}</Text>
          )}
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.author}>{author.display_name || 'Golfer'}</Text>
          <Text style={styles.sub}>{timeAgo(round.created_at)}</Text>
        </View>
        <View style={styles.scorePill}>
          <Text style={styles.scoreNum}>{round.total_score}</Text>
          <Text style={styles.scoreDiff}>{scoreLabel}</Text>
        </View>
      </View>

      {/* Photo hero (only when a photo exists) */}
      {hasPhoto ? (
        <View style={styles.hero}>
          <Image source={{ uri: round.photos[0] }} style={styles.heroImg} contentFit="cover" />
          <LinearGradient
            colors={['transparent', 'rgba(19,42,28,0.85)']}
            style={StyleSheet.absoluteFillObject}
          />
        </View>
      ) : null}

      {/* Course info block (replaces the score/par/holes box) */}
      <Pressable
        testID={`round-card-course-${round.id}`}
        onPress={openCourse}
        style={styles.courseBlock}
      >
        <View style={styles.courseIcon}>
          <Ionicons name="golf-outline" size={20} color={colors.brandPrimary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.courseName} numberOfLines={1}>
            {round.course_name}
          </Text>
          <Text style={styles.courseMeta} numberOfLines={1}>
            {round.holes_played} holes · Par {round.par}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={colors.muted} />
      </Pressable>

      {/* Newly unlocked achievements */}
      {newAchievements.length > 0 ? (
        <View style={styles.achWrap} testID={`round-card-achievements-${round.id}`}>
          {newAchievements.map((a) => (
            <View key={a.key} style={styles.achChip} testID={`round-card-ach-${a.key}`}>
              <View style={styles.achIcon}>
                <Ionicons name={iconFor(a.icon)} size={12} color="#fff" />
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.achChipLabel} numberOfLines={1}>
                  Achievement unlocked
                </Text>
                <Text style={styles.achChipTitle} numberOfLines={1}>
                  {a.title}
                </Text>
              </View>
            </View>
          ))}
        </View>
      ) : null}

      {round.notes ? (
        <MentionText text={round.notes} style={styles.notes} numberOfLines={3} />
      ) : null}

      {/* Action bar */}
      <View style={styles.actions}>
        <Pressable
          testID={`round-card-like-${round.id}`}
          hitSlop={8}
          onPress={() => {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
            onLike();
          }}
          style={styles.actionBtn}
        >
          <Ionicons
            name={round.liked_by_me ? 'heart' : 'heart-outline'}
            size={16}
            color={round.liked_by_me ? colors.brandSecondary : colors.onSurface}
          />
          <Text style={styles.actionText}>{round.like_count}</Text>
        </Pressable>
        <Pressable
          testID={`round-card-comment-${round.id}`}
          hitSlop={8}
          onPress={openPost}
          style={styles.actionBtn}
        >
          <Ionicons name="chatbubble-outline" size={15} color={colors.onSurface} />
          <Text style={styles.actionText}>{round.comment_count}</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        <Text style={styles.subFooter}>{round.weather || ''}</Text>
      </View>
    </Pressable>
  );
}

function timeAgo(iso?: string) {
  if (!iso) return '';
  const d = new Date(iso);
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
  return d.toLocaleDateString();
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.lg,
    ...shadow.card,
    gap: spacing.md,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarImg: { width: '100%', height: '100%' },
  avatarText: { color: colors.onBrandTertiary, fontWeight: '800', fontSize: 15 },
  author: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  sub: { fontSize: 13, color: colors.muted, marginTop: 2 },
  scorePill: {
    backgroundColor: colors.surfaceInverse,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    paddingVertical: 8,
    alignItems: 'center',
  },
  scoreNum: { color: colors.onSurfaceInverse, fontSize: 18, fontWeight: '800', lineHeight: 20 },
  scoreDiff: { color: '#BBE9C9', fontSize: 11, fontWeight: '700', marginTop: -2 },
  hero: {
    height: 180,
    borderRadius: radius.md,
    overflow: 'hidden',
    backgroundColor: colors.surfaceTertiary,
  },
  heroImg: { width: '100%', height: '100%' },
  courseBlock: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  courseIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  courseName: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  courseMeta: { fontSize: 12, color: colors.muted, fontWeight: '600', marginTop: 2 },
  achWrap: { gap: spacing.sm },
  achChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
  },
  achIcon: {
    width: 24,
    height: 24,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  achChipLabel: {
    fontSize: 10,
    fontWeight: '800',
    color: colors.onBrandTertiary,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    opacity: 0.8,
  },
  achChipTitle: { fontSize: 13, fontWeight: '800', color: colors.onBrandTertiary, marginTop: 1 },
  notes: { fontSize: 14, color: colors.onSurface, lineHeight: 20 },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 4 },
  actionText: { fontSize: 13, color: colors.onSurface, fontWeight: '700' },
  subFooter: { fontSize: 12, color: colors.muted, fontWeight: '600' },
});
