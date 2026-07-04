import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing } from '@/src/theme';

type Props = {
  round: any;
  onLike: () => void;
};

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

  return (
    <Pressable
      testID={`round-card-${round.id}`}
      style={styles.card}
      onPress={() => {
        Haptics.selectionAsync().catch(() => {});
        router.push(`/post/${round.id}`);
      }}
    >
      {/* Header */}
      <View style={styles.header}>
        <Pressable
          testID={`round-card-author-${round.id}`}
          onPress={() => author.id && router.push(`/user/${author.id}`)}
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
          <Text style={styles.sub}>
            {round.course_name} · {timeAgo(round.created_at)}
          </Text>
        </View>
        <View style={styles.scorePill}>
          <Text style={styles.scoreNum}>{round.total_score}</Text>
          <Text style={styles.scoreDiff}>{scoreLabel}</Text>
        </View>
      </View>

      {/* Photo or gradient scorecard */}
      {hasPhoto ? (
        <View style={styles.hero}>
          <Image source={{ uri: round.photos[0] }} style={styles.heroImg} contentFit="cover" />
          <LinearGradient
            colors={['transparent', 'rgba(19,42,28,0.85)']}
            style={StyleSheet.absoluteFillObject}
          />
          <View style={styles.heroOverlay}>
            <Text style={styles.heroCourse}>{round.course_name}</Text>
            <Text style={styles.heroMeta}>
              {round.holes_played} holes · Par {round.par}
            </Text>
          </View>
        </View>
      ) : (
        <View style={styles.scorecard}>
          <View style={styles.scorecardStat}>
            <Text style={styles.scorecardLabel}>Score</Text>
            <Text style={styles.scorecardVal}>{round.total_score}</Text>
          </View>
          <View style={styles.scorecardDivider} />
          <View style={styles.scorecardStat}>
            <Text style={styles.scorecardLabel}>vs Par</Text>
            <Text style={styles.scorecardVal}>{scoreLabel}</Text>
          </View>
          <View style={styles.scorecardDivider} />
          <View style={styles.scorecardStat}>
            <Text style={styles.scorecardLabel}>Holes</Text>
            <Text style={styles.scorecardVal}>{round.holes_played}</Text>
          </View>
        </View>
      )}

      {round.notes ? (
        <Text style={styles.notes} numberOfLines={3}>
          {round.notes}
        </Text>
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
            size={22}
            color={round.liked_by_me ? colors.brandSecondary : colors.onSurface}
          />
          <Text style={styles.actionText}>{round.like_count}</Text>
        </Pressable>
        <Pressable
          testID={`round-card-comment-${round.id}`}
          hitSlop={8}
          onPress={() => router.push(`/post/${round.id}`)}
          style={styles.actionBtn}
        >
          <Ionicons name="chatbubble-outline" size={20} color={colors.onSurface} />
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
    height: 200,
    borderRadius: radius.md,
    overflow: 'hidden',
    backgroundColor: colors.surfaceTertiary,
  },
  heroImg: { width: '100%', height: '100%' },
  heroOverlay: { position: 'absolute', left: spacing.md, right: spacing.md, bottom: spacing.md },
  heroCourse: { color: '#fff', fontSize: 20, fontWeight: '800' },
  heroMeta: { color: '#DCFCE7', fontSize: 13, fontWeight: '600', marginTop: 2 },
  scorecard: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.md,
    paddingVertical: spacing.lg,
    alignItems: 'center',
  },
  scorecardStat: { flex: 1, alignItems: 'center' },
  scorecardDivider: { width: 1, backgroundColor: colors.border, alignSelf: 'stretch', marginVertical: spacing.sm },
  scorecardLabel: { fontSize: 11, color: colors.muted, fontWeight: '700', letterSpacing: 0.6, textTransform: 'uppercase' },
  scorecardVal: { fontSize: 22, color: colors.onSurface, fontWeight: '800', marginTop: 2 },
  notes: { fontSize: 14, color: colors.onSurface, lineHeight: 20 },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 4 },
  actionText: { fontSize: 14, color: colors.onSurface, fontWeight: '700' },
  subFooter: { fontSize: 12, color: colors.muted, fontWeight: '600' },
});
