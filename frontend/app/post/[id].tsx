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
import { colors, radius, shadow, spacing } from '@/src/theme';
import { api } from '@/src/api';
import { MentionInput } from '@/src/components/MentionInput';
import { HoleGrid } from '@/src/components/HoleGrid';
import { useAuth } from '@/src/auth-context';

export default function PostDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const [round, setRound] = useState<any>(null);
  const [comments, setComments] = useState<any[] | null>(null);
  const [text, setText] = useState('');
  const [mentions, setMentions] = useState<string[]>([]);
  const [posting, setPosting] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [pinLoading, setPinLoading] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [r, c] = await Promise.all([api.getRound(String(id)), api.getComments(String(id))]);
      setRound(r);
      setComments(c);
      // Check if this round is the user's pinned round
      if (user && r.author?.id === user.id) {
        try {
          const me = await api.getUser(user.id);
          setPinned(me?.pinned_round?.id === r.id);
        } catch {}
      }
    } catch {}
  }, [id, user]);

  useEffect(() => {
    load();
  }, [load]);

  const onLike = async () => {
    if (!round) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    setRound({
      ...round,
      liked_by_me: !round.liked_by_me,
      like_count: round.liked_by_me ? Math.max(0, round.like_count - 1) : round.like_count + 1,
    });
    try {
      const res = await api.toggleLike(String(id));
      setRound((prev: any) => ({ ...prev, liked_by_me: res.liked, like_count: res.like_count }));
    } catch {}
  };

  const onSubmit = async () => {
    if (!text.trim()) return;
    setPosting(true);
    try {
      const c = await api.addComment(String(id), text.trim(), mentions);
      setComments((prev) => [...(prev || []), c]);
      setText('');
      setMentions([]);
      setRound((prev: any) => (prev ? { ...prev, comment_count: prev.comment_count + 1 } : prev));
    } catch {
    } finally {
      setPosting(false);
    }
  };

  const togglePin = async () => {
    if (!round || pinLoading) return;
    setPinLoading(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    try {
      if (pinned) {
        await api.unpinRound();
        setPinned(false);
      } else {
        await api.pinRound(round.id);
        setPinned(true);
      }
    } catch {
    } finally {
      setPinLoading(false);
    }
  };

  if (!round) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} size="large" />
      </View>
    );
  }

  const hasPhoto = round.photos && round.photos.length > 0;
  const scoreDiff = round.total_score - (round.par || 72);
  const scoreLabel = scoreDiff === 0 ? 'Even' : scoreDiff > 0 ? `+${scoreDiff}` : `${scoreDiff}`;
  const author = round.author || {};
  const initials = (author.display_name || 'G')
    .split(' ')
    .map((s: string) => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <View style={styles.container} testID="post-detail-screen">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView
          contentContainerStyle={{ paddingBottom: 100 }}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.hero}>
            {hasPhoto ? (
              <Image source={{ uri: round.photos[0] }} style={StyleSheet.absoluteFillObject} contentFit="cover" />
            ) : (
              <View style={[StyleSheet.absoluteFillObject, { backgroundColor: colors.surfaceInverse }]} />
            )}
            <LinearGradient
              colors={['rgba(19,42,28,0.2)', 'rgba(19,42,28,0.85)']}
              style={StyleSheet.absoluteFillObject}
            />
            <SafeAreaView edges={['top']} style={styles.heroTopBar}>
              <Pressable testID="post-back" onPress={() => router.back()} style={styles.iconBtn} hitSlop={8}>
                <Ionicons name="chevron-back" size={22} color="#fff" />
              </Pressable>
              <View style={{ flex: 1 }} />
              {user && round.author?.id === user.id ? (
                <Pressable
                  testID="post-pin-toggle"
                  onPress={togglePin}
                  style={[styles.pinBtn, pinned && styles.pinBtnOn]}
                  hitSlop={8}
                >
                  {pinLoading ? (
                    <ActivityIndicator size="small" color="#fff" />
                  ) : (
                    <>
                      <Ionicons name={pinned ? 'pin' : 'pin-outline'} size={16} color="#fff" />
                      <Text style={styles.pinBtnText}>{pinned ? 'Pinned' : 'Pin to profile'}</Text>
                    </>
                  )}
                </Pressable>
              ) : null}
            </SafeAreaView>
            <View style={styles.heroCopy}>
              <Text style={styles.heroCourse}>{round.course_name}</Text>
              <Text style={styles.heroDate}>
                {new Date(round.date || round.created_at).toLocaleDateString(undefined, {
                  month: 'long',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </Text>
            </View>
          </View>

          <View style={styles.body}>
            <Pressable
              testID="post-author"
              onPress={() => router.push(`/user/${author.id}`)}
              style={styles.authorRow}
            >
              <View style={styles.avatar}>
                {author.avatar ? (
                  <Image source={{ uri: author.avatar }} style={{ width: '100%', height: '100%' }} />
                ) : (
                  <Text style={styles.avatarText}>{initials}</Text>
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.authorName}>{author.display_name || 'Golfer'}</Text>
                <Text style={styles.authorSub}>
                  {author.handicap != null ? `HC ${author.handicap}` : 'Golfer'}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>

            <View style={styles.scoreCard}>
              <View style={styles.scoreCell}>
                <Text style={styles.scoreValBig}>{round.total_score}</Text>
                <Text style={styles.scoreLbl}>Score</Text>
              </View>
              <View style={styles.scoreDivider} />
              <View style={styles.scoreCell}>
                <Text style={styles.scoreValBig}>{scoreLabel}</Text>
                <Text style={styles.scoreLbl}>vs Par</Text>
              </View>
              <View style={styles.scoreDivider} />
              <View style={styles.scoreCell}>
                <Text style={styles.scoreValBig}>{round.holes_played}</Text>
                <Text style={styles.scoreLbl}>Holes</Text>
              </View>
              <View style={styles.scoreDivider} />
              <View style={styles.scoreCell}>
                <Text style={styles.scoreValBig}>{round.par}</Text>
                <Text style={styles.scoreLbl}>Par</Text>
              </View>
            </View>

            {(round.fairways_hit != null || round.greens_in_regulation != null || round.putts != null) ? (
              <View style={styles.miniStats}>
                {round.fairways_hit != null && (
                  <MiniStat label="Fairways" value={String(round.fairways_hit)} />
                )}
                {round.greens_in_regulation != null && (
                  <MiniStat label="GIR" value={String(round.greens_in_regulation)} />
                )}
                {round.putts != null && <MiniStat label="Putts" value={String(round.putts)} />}
              </View>
            ) : null}

            {round.hole_scores && round.hole_scores.length === 18 ? (
              <View testID="post-hole-grid" style={styles.holeCard}>
                <Text style={styles.holeCardTitle}>Scorecard</Text>
                <HoleGrid
                  scores={round.hole_scores.map((n: number) => String(n))}
                  pars={round.hole_pars && round.hole_pars.length === 18 ? round.hole_pars : undefined}
                  readOnly
                />
              </View>
            ) : null}

            {round.notes ? <Text style={styles.notes}>{round.notes}</Text> : null}

            <View style={styles.actions}>
              <Pressable testID="post-like" onPress={onLike} style={styles.actionBtn} hitSlop={6}>
                <Ionicons
                  name={round.liked_by_me ? 'heart' : 'heart-outline'}
                  size={22}
                  color={round.liked_by_me ? colors.brandSecondary : colors.onSurface}
                />
                <Text style={styles.actionText}>{round.like_count} likes</Text>
              </Pressable>
              <View style={styles.actionBtn}>
                <Ionicons name="chatbubble-outline" size={20} color={colors.onSurface} />
                <Text style={styles.actionText}>{round.comment_count} comments</Text>
              </View>
            </View>

            <View style={styles.commentsSection}>
              <Text style={styles.sectionTitle}>Comments</Text>
              {comments && comments.length > 0 ? (
                comments.map((c) => <CommentRow key={c.id} c={c} />)
              ) : (
                <Text style={styles.emptyComments}>Be the first to say something nice.</Text>
              )}
            </View>
          </View>
        </ScrollView>

        <SafeAreaView edges={['bottom']} style={styles.commentBarSafe}>
          <View style={styles.commentBar}>
            <View style={{ flex: 1 }}>
              <MentionInput
                testID="post-comment-input"
                value={text}
                onChangeText={setText}
                onMentionsChange={setMentions}
                placeholder="Add a comment — try @name"
                style={styles.commentInput}
                multiline
              />
            </View>
            <Pressable
              testID="post-comment-send"
              onPress={onSubmit}
              style={[styles.sendBtn, (!text.trim() || posting) && { opacity: 0.5 }]}
              disabled={!text.trim() || posting}
            >
              <Ionicons name="send" size={18} color="#fff" />
            </Pressable>
          </View>
        </SafeAreaView>
      </KeyboardAvoidingView>
    </View>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.miniStatPill}>
      <Text style={styles.miniStatVal}>{value}</Text>
      <Text style={styles.miniStatLabel}>{label}</Text>
    </View>
  );
}

function CommentRow({ c }: { c: any }) {
  const initials = (c.author?.display_name || 'G')
    .split(' ')
    .map((s: string) => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  const parts = String(c.text || '').split(/(@\S+)/g);
  return (
    <View style={styles.commentRow}>
      <View style={styles.commentAvatar}>
        {c.author?.avatar ? (
          <Image source={{ uri: c.author.avatar }} style={{ width: '100%', height: '100%' }} />
        ) : (
          <Text style={styles.commentAvatarText}>{initials}</Text>
        )}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.commentAuthor}>{c.author?.display_name || 'Golfer'}</Text>
        <Text style={styles.commentText}>
          {parts.map((p, i) =>
            p.startsWith('@') ? (
              <Text key={i} style={styles.mention}>
                {p}
              </Text>
            ) : (
              <Text key={i}>{p}</Text>
            ),
          )}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  hero: { height: 280 },
  heroTopBar: { flexDirection: 'row', paddingHorizontal: spacing.lg, alignItems: 'center' },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(0,0,0,0.35)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  pinBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  pinBtnOn: { backgroundColor: colors.brandDeep },
  pinBtnText: { color: '#fff', fontWeight: '800', fontSize: 12 },
  heroCopy: { position: 'absolute', left: spacing.xl, right: spacing.xl, bottom: spacing.xl },
  heroCourse: { color: '#fff', fontSize: 28, fontWeight: '800' },
  heroDate: { color: '#DCFCE7', fontSize: 14, fontWeight: '600', marginTop: 4 },
  body: { padding: spacing.xl, gap: spacing.lg, marginTop: -20, backgroundColor: colors.surface },
  authorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    ...shadow.soft,
  },
  avatar: {
    width: 46,
    height: 46,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarText: { color: colors.onBrandTertiary, fontWeight: '800', fontSize: 15 },
  authorName: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  authorSub: { fontSize: 13, color: colors.muted, marginTop: 2 },
  scoreCard: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceInverse,
    borderRadius: radius.lg,
    padding: spacing.lg,
    alignItems: 'center',
  },
  scoreCell: { flex: 1, alignItems: 'center' },
  scoreDivider: { width: 1, backgroundColor: 'rgba(255,255,255,0.15)', alignSelf: 'stretch' },
  scoreValBig: { fontSize: 26, fontWeight: '800', color: '#fff' },
  scoreLbl: {
    fontSize: 11,
    color: '#BBE9C9',
    fontWeight: '700',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    marginTop: 2,
  },
  miniStats: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  miniStatPill: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 6,
    backgroundColor: colors.brandTertiary,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
  },
  miniStatVal: { fontSize: 15, fontWeight: '800', color: colors.onBrandTertiary },
  miniStatLabel: { fontSize: 12, color: colors.onBrandTertiary, fontWeight: '600' },
  notes: {
    fontSize: 15,
    lineHeight: 22,
    color: colors.onSurface,
    backgroundColor: colors.surfaceSecondary,
    padding: spacing.lg,
    borderRadius: radius.lg,
    ...shadow.soft,
  },
  actions: { flexDirection: 'row', gap: spacing.xl, paddingVertical: spacing.sm },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  actionText: { fontSize: 14, fontWeight: '700', color: colors.onSurface },
  commentsSection: { gap: spacing.md, marginTop: spacing.md },
  sectionTitle: { fontSize: 17, fontWeight: '800', color: colors.onSurface },
  emptyComments: { color: colors.muted, fontSize: 14, fontStyle: 'italic' },
  commentRow: { flexDirection: 'row', gap: spacing.md, paddingVertical: spacing.sm },
  commentAvatar: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  commentAvatarText: { color: colors.onBrandTertiary, fontWeight: '800', fontSize: 12 },
  commentAuthor: { fontSize: 13, fontWeight: '800', color: colors.onSurface },
  commentText: { fontSize: 14, color: colors.onSurface, marginTop: 2, lineHeight: 20 },
  mention: { color: colors.brandPrimary, fontWeight: '800' },
  holeCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.md,
    ...shadow.soft,
    gap: spacing.sm,
  },
  holeCardTitle: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  commentBarSafe: {
    borderTopWidth: 1,
    borderTopColor: colors.divider,
    backgroundColor: colors.surface,
  },
  commentBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: spacing.md,
    gap: spacing.sm,
  },
  commentInput: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.onSurface,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadow.soft,
  },
});
