import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  ActivityIndicator,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, IMAGES, radius, shadow, spacing } from '@/src/theme';
import { api } from '@/src/api';
import { RoundCard } from '@/src/components/RoundCard';
import { TBButton } from '@/src/components/TBButton';

export default function UserDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [profile, setProfile] = useState<any>(null);
  const [rounds, setRounds] = useState<any[] | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [p, r] = await Promise.all([api.getUser(String(id)), api.getUserRounds(String(id))]);
      setProfile(p);
      setRounds(r);
    } catch {}
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleFollow = async () => {
    if (!profile) return;
    setProfile({
      ...profile,
      is_following: !profile.is_following,
      follower_count: profile.is_following
        ? Math.max(0, profile.follower_count - 1)
        : profile.follower_count + 1,
    });
    try {
      await api.toggleFollow(String(id));
    } catch {}
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
    <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: 60 }} testID="user-detail-screen">
      <View style={styles.cover}>
        <Image source={{ uri: IMAGES.courseThumb }} style={StyleSheet.absoluteFillObject} contentFit="cover" />
        <LinearGradient
          colors={['rgba(19,42,28,0.15)', 'rgba(19,42,28,0.8)']}
          style={StyleSheet.absoluteFillObject}
        />
        <SafeAreaView edges={['top']} style={styles.coverTop}>
          <Pressable testID="user-back" onPress={() => router.back()} style={styles.iconBtn} hitSlop={8}>
            <Ionicons name="chevron-back" size={22} color="#fff" />
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
        <Text style={styles.homeCourse}>{profile.home_course || 'No home course'}</Text>
        {profile.bio ? <Text style={styles.bio}>{profile.bio}</Text> : null}
      </View>

      <View style={styles.statsRow}>
        <StatCell label="Handicap" value={profile.handicap != null ? String(profile.handicap) : '—'} />
        <StatCell label="Rounds" value={String(profile.round_count || 0)} />
        <StatCell label="Followers" value={String(profile.follower_count || 0)} />
        <StatCell label="Best" value={profile.best_score != null ? String(profile.best_score) : '—'} />
      </View>

      {!profile.is_me ? (
        <View style={styles.followWrap}>
          <TBButton
            label={profile.is_following ? 'Following' : 'Follow'}
            testID="user-follow-btn"
            onPress={toggleFollow}
            variant={profile.is_following ? 'secondary' : 'primary'}
          />
        </View>
      ) : null}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Rounds</Text>
        {rounds && rounds.length > 0 ? (
          rounds.map((r) => <RoundCard key={r.id} round={r} onLike={() => onLike(r.id)} />)
        ) : (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyTitle}>No rounds yet</Text>
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

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  cover: { height: 220, backgroundColor: colors.surfaceInverse },
  coverTop: { flexDirection: 'row', paddingHorizontal: spacing.lg, alignItems: 'center' },
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
  statVal: { fontSize: 20, fontWeight: '800', color: colors.brandPrimary },
  statLbl: {
    fontSize: 11,
    color: colors.muted,
    fontWeight: '700',
    letterSpacing: 0.4,
    marginTop: 2,
    textTransform: 'uppercase',
  },
  followWrap: { paddingHorizontal: spacing.lg, marginTop: spacing.lg },
  section: { marginTop: spacing.xl, paddingHorizontal: spacing.lg },
  sectionTitle: { fontSize: 18, fontWeight: '800', color: colors.onSurface, marginBottom: spacing.md },
  emptyBox: {
    padding: spacing.xl,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    alignItems: 'center',
  },
  emptyTitle: { fontSize: 15, fontWeight: '800', color: colors.onSurface },
});
