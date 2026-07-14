import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  ActivityIndicator,
  Pressable,
  Platform,
} from 'react-native';
import { Image } from 'expo-image';
import { useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, IMAGES, radius, shadow, spacing } from '@/src/theme';
import { api } from '@/src/api';
import { RoundCard } from '@/src/components/RoundCard';
import { FeedNativeAd } from '@/src/components/FeedNativeAd';
import { useAuth } from '@/src/auth-context';
import { TBButton } from '@/src/components/TBButton';

type FeedFilter = 'all' | 'round' | 'text' | 'lfg';
const FILTERS: { key: FeedFilter; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: 'all', label: 'All', icon: 'sparkles' },
  { key: 'round', label: 'Rounds', icon: 'golf' },
  { key: 'text', label: 'Chat', icon: 'chatbubble-ellipses' },
  { key: 'lfg', label: 'LFG', icon: 'people' },
];

export default function Feed() {
  const router = useRouter();
  const { user } = useAuth();
  const [rounds, setRounds] = useState<any[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState(0);
  const [filter, setFilter] = useState<FeedFilter>('all');

  const load = useCallback(async () => {
    setError(null);
    try {
      const [data, notif] = await Promise.all([
        api.feed('followers'),
        api.listNotifications().catch(() => ({ unread: 0, notifications: [] })),
      ]);
      setRounds(data);
      setUnread(notif.unread || 0);
    } catch (e: any) {
      setError(e?.message || 'Failed to load feed');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const onLike = async (id: string) => {
    if (!rounds) return;
    // Optimistic
    setRounds(
      rounds.map((r) =>
        r.id === id
          ? {
              ...r,
              liked_by_me: !r.liked_by_me,
              like_count: r.liked_by_me ? Math.max(0, r.like_count - 1) : r.like_count + 1,
            }
          : r,
      ),
    );
    try {
      const res = await api.toggleLike(id);
      setRounds((prev) =>
        prev
          ? prev.map((r) =>
              r.id === id ? { ...r, liked_by_me: res.liked, like_count: res.like_count } : r,
            )
          : prev,
      );
    } catch {}
  };

  const header = (
    <SafeAreaView edges={['top']} style={styles.headerSafe}>
      <View style={styles.headerRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.hello}>Hi {user?.display_name?.split(' ')[0] || 'Golfer'}</Text>
          <Text style={styles.headerTitle}>The Feed</Text>
        </View>
        <Pressable
          testID="header-notifications"
          onPress={() => router.push('/notifications')}
          style={styles.bellBtn}
          hitSlop={6}
        >
          <Ionicons name="notifications-outline" size={22} color={colors.onSurface} />
          {unread > 0 ? (
            <View style={styles.bellBadge}>
              <Text style={styles.bellBadgeText}>{unread > 9 ? '9+' : String(unread)}</Text>
            </View>
          ) : null}
        </Pressable>
        <Pressable
          testID="header-my-profile"
          onPress={() => router.push('/(tabs)/profile')}
          style={styles.headerCta}
        >
          <Ionicons name="person" size={18} color="#fff" />
          <Text style={styles.headerCtaText}>My Profile</Text>
        </Pressable>
      </View>
      <View style={styles.filterRow} testID="feed-filter-row">
        {FILTERS.map((f) => {
          const active = filter === f.key;
          return (
            <Pressable
              key={f.key}
              testID={`feed-filter-${f.key}`}
              onPress={() => setFilter(f.key)}
              hitSlop={4}
              style={[styles.filterPill, active && styles.filterPillActive]}
            >
              <Ionicons
                name={f.icon}
                size={12}
                color={active ? '#fff' : colors.onSurface}
              />
              <Text style={[styles.filterPillText, active && styles.filterPillTextActive]}>
                {f.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </SafeAreaView>
  );

  if (rounds === null) {
    return (
      <View style={styles.center}>
        {header}
        <ActivityIndicator color={colors.brandPrimary} size="large" style={{ marginTop: 60 }} />
      </View>
    );
  }

  const visibleRounds =
    filter === 'all'
      ? rounds
      : rounds.filter((r) => (r.post_type || 'round') === filter);

  return (
    <View style={styles.container} testID="feed-screen">
      <View style={styles.headerGlass}>
        {Platform.OS === 'ios' ? (
          <BlurView intensity={80} tint="light" style={StyleSheet.absoluteFill} />
        ) : (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(253,252,248,0.96)' }]} />
        )}
        {header}
      </View>

      <FlatList
        data={visibleRounds}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.brandPrimary}
            colors={[colors.brandPrimary]}
            progressViewOffset={HEADER_H}
          />
        }
        renderItem={({ item, index }) => (
          <>
            {/* Ad slot: after every 5th real post so ads are visible only once
                the user has seen a few genuine rounds first. */}
            {index > 0 && index % 5 === 0 ? <FeedNativeAd /> : null}
            <RoundCard
              round={item}
              onLike={() => onLike(item.id)}
              onDeleted={(id) => setRounds((prev) => prev.filter((r) => r.id !== id))}
            />
          </>
        )}
        ListHeaderComponent={<VerifyBanner />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Image source={{ uri: IMAGES.emptyFeed }} style={styles.emptyImg} contentFit="cover" />
            <Text style={styles.emptyTitle}>
              {filter === 'all' ? 'Your feed is quiet' : `No ${filterLabel(filter)} posts yet`}
            </Text>
            <Text style={styles.emptySub}>
              {filter === 'all'
                ? 'Follow other golfers from Discover, or log your own round to start the conversation.'
                : `Try switching filters, or be the first to post ${filterLabel(filter)}.`}
            </Text>
            <TBButton label="Log a round" testID="empty-log-round" onPress={() => router.push('/(tabs)/log')} />
            <Pressable
              testID="empty-find-golfers"
              onPress={() => router.push('/(tabs)/discover')}
              style={{ marginTop: spacing.sm }}
            >
              <Text style={{ color: colors.brandPrimary, fontWeight: '800' }}>Find golfers to follow</Text>
            </Pressable>
          </View>
        }
        ListFooterComponent={
          error ? (
            <View style={styles.errBanner}>
              <Text style={styles.errText}>{error}</Text>
              <TBButton label="Retry" variant="secondary" onPress={load} />
            </View>
          ) : null
        }
      />
    </View>
  );
}

const HEADER_H = Platform.OS === 'ios' ? 168 : 158;

function filterLabel(f: 'round' | 'text' | 'lfg') {
  return f === 'round' ? 'round' : f === 'text' ? 'chat' : 'LFG';
}

function VerifyBanner() {
  const { user } = useAuth();
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // `email_verified` is true for legacy accounts by default; only show banner
  // when the flag is explicitly false.
  if (!user || user.email_verified !== false || !user.email) return null;
  const resend = async () => {
    setErr(null);
    setSending(true);
    try {
      await api.resendVerification(user.email!);
      setSent(true);
    } catch (e: any) {
      setErr(e?.message || 'Could not resend verification email.');
    } finally {
      setSending(false);
    }
  };
  return (
    <View style={styles.verifyBanner} testID="verify-banner">
      <View style={styles.verifyIcon}>
        <Ionicons name="mail-unread" size={18} color="#8B5A00" />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.verifyTitle}>Verify your email</Text>
        <Text style={styles.verifySub}>
          {sent
            ? "We just resent the link. Check your inbox (and spam)."
            : `We sent a link to ${user.email}. Tap it to confirm your account.`}
        </Text>
        {err ? <Text style={styles.verifyErr}>{err}</Text> : null}
      </View>
      {!sent ? (
        <Pressable
          testID="verify-banner-resend"
          onPress={resend}
          hitSlop={8}
          style={styles.verifyBtn}
          disabled={sending}
        >
          <Text style={styles.verifyBtnText}>{sending ? '…' : 'Resend'}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, backgroundColor: colors.surface },
  headerGlass: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 5,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
  },
  headerSafe: {},
  headerRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.md,
    gap: spacing.md,
  },
  hello: { fontSize: 13, color: colors.muted, fontWeight: '700', letterSpacing: 0.4 },
  headerTitle: { fontSize: 28, fontWeight: '800', color: colors.onSurface, marginTop: 2 },
  headerCta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radius.pill,
    ...shadow.soft,
  },
  headerCtaText: { color: '#fff', fontWeight: '800', fontSize: 13 },
  bellBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bellBadge: {
    position: 'absolute',
    top: 2,
    right: 2,
    minWidth: 18,
    height: 18,
    paddingHorizontal: 4,
    borderRadius: 9,
    backgroundColor: '#c0392b',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: colors.surface,
  },
  bellBadgeText: { fontSize: 10, fontWeight: '800', color: '#fff' },
  filterRow: {
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.md,
  },
  filterPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceTertiary,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  filterPillActive: {
    backgroundColor: colors.brandPrimary,
    borderColor: colors.brandPrimary,
  },
  filterPillText: {
    fontSize: 12,
    fontWeight: '800',
    color: colors.onSurface,
    letterSpacing: 0.2,
  },
  filterPillTextActive: { color: '#fff' },
  listContent: {
    paddingTop: HEADER_H + spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingBottom: 140,
  },
  empty: {
    alignItems: 'center',
    padding: spacing.xl,
    gap: spacing.md,
  },
  emptyImg: { width: 180, height: 180, borderRadius: radius.lg, marginBottom: spacing.md },
  emptyTitle: { fontSize: 20, fontWeight: '800', color: colors.onSurface },
  emptySub: { fontSize: 14, color: colors.muted, textAlign: 'center', maxWidth: 300, marginBottom: spacing.md },
  errBanner: { padding: spacing.lg, gap: spacing.md },
  errText: { color: colors.error, textAlign: 'center', fontWeight: '600' },
  verifyBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginHorizontal: spacing.md,
    marginBottom: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: '#FFF4D6',
    borderWidth: 1,
    borderColor: '#F0DBA0',
  },
  verifyIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    backgroundColor: '#FCE7B6',
    alignItems: 'center',
    justifyContent: 'center',
  },
  verifyTitle: { fontSize: 13, fontWeight: '800', color: '#7A4E00' },
  verifySub: { fontSize: 12, color: '#7A4E00', marginTop: 2, lineHeight: 16 },
  verifyErr: { fontSize: 11, color: '#8B1D1A', marginTop: 4, fontWeight: '700' },
  verifyBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: '#8B5A00',
  },
  verifyBtnText: { color: '#fff', fontWeight: '800', fontSize: 12 },
});
