import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, IMAGES, radius, shadow, spacing } from '@/src/theme';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth-context';
import { TBButton } from '@/src/components/TBButton';
import { RoundCard } from '@/src/components/RoundCard';
import { WishlistList } from '@/src/components/WishlistList';

export default function Profile() {
  const router = useRouter();
  const { user, signOut, refresh } = useAuth();
  const [profile, setProfile] = useState<any>(null);
  const [rounds, setRounds] = useState<any[] | null>(null);
  const [achievements, setAchievements] = useState<any | null>(null);
  const [wishlist, setWishlist] = useState<any[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    try {
      const [p, r, a, w] = await Promise.all([
        api.getUser(user.id),
        api.getUserRounds(user.id),
        api.getUserAchievements(user.id),
        api.getUserWishlist(user.id),
      ]);
      setProfile(p);
      setRounds(r);
      setAchievements(a);
      setWishlist(w);
    } catch {}
  }, [user]);

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
    await refresh();
    await load();
    setRefreshing(false);
  };

  const onLike = async (id: string) => {
    if (!rounds) return;
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

  if (!profile) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} size="large" />
      </View>
    );
  }

  const initials = (profile.display_name || 'G')
    .split(' ')
    .map((s: string) => s[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <ScrollView
      testID="profile-screen"
      style={styles.container}
      contentContainerStyle={{ paddingBottom: 140 }}
      showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      <View style={styles.cover}>
        <Image source={{ uri: IMAGES.courseThumb }} style={StyleSheet.absoluteFillObject} contentFit="cover" />
        <LinearGradient
          colors={['rgba(19,42,28,0.1)', 'rgba(19,42,28,0.6)', 'rgba(19,42,28,0.9)']}
          style={StyleSheet.absoluteFillObject}
        />
        <SafeAreaView edges={['top']} style={styles.coverTopBar}>
          <View style={{ flex: 1 }} />
          <Pressable
            testID="profile-signout"
            onPress={signOut}
            style={styles.iconBtn}
            hitSlop={8}
          >
            <Ionicons name="log-out-outline" size={20} color="#fff" />
          </Pressable>
        </SafeAreaView>
      </View>

      <View style={styles.avatarWrap}>
        <View style={styles.avatar}>
          {profile.avatar ? (
            <Image source={{ uri: profile.avatar }} style={{ width: '100%', height: '100%' }} />
          ) : (
            <Text style={styles.avatarText}>{initials}</Text>
          )}
        </View>
      </View>

      <View style={styles.identity}>
        <Text style={styles.name}>{profile.display_name}</Text>
        <Text style={styles.homeCourse}>{profile.home_course || 'No home course yet'}</Text>
        {profile.bio ? <Text style={styles.bio}>{profile.bio}</Text> : null}
      </View>

      <View style={styles.statsRow}>
        <StatCell label="Handicap" value={profile.handicap != null ? String(profile.handicap) : '—'} />
        <StatCell label="Rounds" value={String(profile.round_count || 0)} />
        <StatCell
          label="Avg"
          value={profile.avg_score != null ? String(profile.avg_score) : '—'}
        />
        <StatCell
          label="Best"
          value={profile.best_score != null ? String(profile.best_score) : '—'}
        />
      </View>

      <View style={styles.actionsRow}>
        <TBButton
          label="Log a round"
          testID="profile-log-cta"
          onPress={() => router.push('/(tabs)/log')}
          style={{ flex: 1 }}
        />
      </View>

      {achievements && achievements.achievements ? (
        <View style={styles.section} testID="profile-achievements">
          <View style={styles.sectionHeaderRow}>
            <Text style={styles.sectionTitle}>Achievements</Text>
            <Text style={styles.sectionCount}>{achievements.total}/{achievements.achievements.length}</Text>
          </View>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.achRow}
          >
            {achievements.achievements.map((a: any) => (
              <View
                key={a.key}
                testID={`achievement-${a.key}`}
                style={[styles.achCard, !a.earned && styles.achCardLocked]}
              >
                <View style={[styles.achIcon, !a.earned && styles.achIconLocked]}>
                  <Ionicons
                    name={a.earned ? iconFor(a.icon) : 'lock-closed'}
                    size={22}
                    color={a.earned ? '#fff' : colors.muted}
                  />
                </View>
                <Text style={[styles.achTitle, !a.earned && { color: colors.muted }]}>{a.title}</Text>
                <Text style={styles.achDesc} numberOfLines={2}>
                  {a.desc}
                </Text>
              </View>
            ))}
          </ScrollView>
        </View>
      ) : null}

      <View style={styles.section} testID="profile-wishlist">
        <View style={styles.sectionHeaderRow}>
          <Text style={styles.sectionTitle}>Wishlist</Text>
          <Text style={styles.sectionCount}>{wishlist?.length ?? 0}</Text>
        </View>
        <WishlistList
          items={wishlist || []}
          onRemove={async (course) => {
            setWishlist((prev) => (prev || []).filter((w) => w.course_name !== course));
            try {
              await api.removeWishlist(course);
            } catch {
              // reload to restore truth
              load();
            }
          }}
          emptyLabel="Bookmark courses from Discover to build your wishlist."
        />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Your rounds</Text>
        {rounds && rounds.length > 0 ? (
          rounds.map((r) => <RoundCard key={r.id} round={r} onLike={() => onLike(r.id)} />)
        ) : (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyTitle}>No rounds logged yet</Text>
            <Text style={styles.emptySub}>Save your first scorecard and it'll show up here.</Text>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.statCell}>
      <Text style={styles.statVal}>{value}</Text>
      <Text style={styles.statLbl}>{label}</Text>
    </View>
  );
}

function iconFor(key: string): any {
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

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  cover: { height: 220, backgroundColor: colors.surfaceInverse },
  coverTopBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
  },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(0,0,0,0.35)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarWrap: { alignItems: 'center', marginTop: -50 },
  avatar: {
    width: 100,
    height: 100,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 5,
    borderColor: colors.surface,
    overflow: 'hidden',
    ...shadow.card,
  },
  avatarText: { fontSize: 34, fontWeight: '800', color: colors.onBrandTertiary },
  identity: { alignItems: 'center', paddingHorizontal: spacing.xl, marginTop: spacing.md, gap: 4 },
  name: { fontSize: 24, fontWeight: '800', color: colors.onSurface },
  homeCourse: { fontSize: 14, color: colors.muted, fontWeight: '600' },
  bio: { fontSize: 14, color: colors.onSurface, textAlign: 'center', marginTop: spacing.sm },
  statsRow: {
    flexDirection: 'row',
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.md,
    ...shadow.soft,
  },
  statCell: { flex: 1, alignItems: 'center' },
  statVal: { fontSize: 22, fontWeight: '800', color: colors.brandPrimary },
  statLbl: {
    fontSize: 11,
    color: colors.muted,
    fontWeight: '700',
    letterSpacing: 0.4,
    marginTop: 2,
    textTransform: 'uppercase',
  },
  actionsRow: { flexDirection: 'row', paddingHorizontal: spacing.lg, marginTop: spacing.lg, gap: spacing.md },
  section: { marginTop: spacing.xl, paddingHorizontal: spacing.lg },
  sectionTitle: { fontSize: 18, fontWeight: '800', color: colors.onSurface, marginBottom: spacing.md },
  sectionHeaderRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sectionCount: {
    fontSize: 12,
    fontWeight: '800',
    color: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: radius.pill,
    marginBottom: spacing.md,
  },
  achRow: { gap: spacing.md, paddingRight: spacing.lg },
  achCard: {
    width: 140,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    gap: 6,
    ...shadow.soft,
  },
  achCardLocked: { backgroundColor: colors.surfaceTertiary },
  achIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  achIconLocked: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  achTitle: { fontSize: 13, fontWeight: '800', color: colors.onSurface },
  achDesc: { fontSize: 11, color: colors.muted, lineHeight: 15 },
  emptyBox: {
    padding: spacing.xl,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    alignItems: 'center',
    gap: 6,
  },
  emptyTitle: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
  emptySub: { fontSize: 13, color: colors.muted, textAlign: 'center' },
});
