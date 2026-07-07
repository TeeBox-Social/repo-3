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
import { useAuth } from '@/src/auth-context';
import { TBButton } from '@/src/components/TBButton';

export default function Feed() {
  const router = useRouter();
  const { user } = useAuth();
  const [rounds, setRounds] = useState<any[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState(0);

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
          testID="header-log-round"
          onPress={() => router.push('/(tabs)/log')}
          style={styles.headerCta}
        >
          <Ionicons name="add" size={20} color="#fff" />
          <Text style={styles.headerCtaText}>Log round</Text>
        </Pressable>
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
        data={rounds}
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
        renderItem={({ item }) => <RoundCard round={item} onLike={() => onLike(item.id)} />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Image source={{ uri: IMAGES.emptyFeed }} style={styles.emptyImg} contentFit="cover" />
            <Text style={styles.emptyTitle}>Your feed is quiet</Text>
            <Text style={styles.emptySub}>
              Follow other golfers from Discover, or log your own round to start the conversation.
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

const HEADER_H = Platform.OS === 'ios' ? 120 : 110;

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
  listContent: {
    paddingTop: HEADER_H + spacing.md,
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
});
