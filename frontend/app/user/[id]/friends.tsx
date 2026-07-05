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
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { api } from '@/src/api';

export default function FriendsList() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [friends, setFriends] = useState<any[] | null>(null);
  const [owner, setOwner] = useState<any>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [list, prof] = await Promise.all([api.getUserFriends(String(id)), api.getUser(String(id))]);
      setFriends(list);
      setOwner(prof);
    } catch {}
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleFollow = async (fid: string) => {
    if (!friends) return;
    setFriends(
      friends.map((f) =>
        f.id === fid
          ? {
              ...f,
              is_following: !f.is_following,
              // If we now follow them AND they already follow us → we're friends
              is_friend: !f.is_following ? f.is_friend || false : false,
            }
          : f,
      ),
    );
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    try {
      await api.toggleFollow(fid);
      // Refetch to get true is_friend state (server knows if they follow me back)
      const fresh = await api.getUserFriends(String(id));
      setFriends(fresh);
    } catch {}
  };

  if (!friends || !owner) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} size="large" />
      </View>
    );
  }

  const mutualCount = friends.filter((f) => f.is_friend && !f.is_me).length;
  const firstName = owner.display_name?.split(' ')[0] || 'Their';

  return (
    <View style={styles.container} testID="friends-screen">
      <SafeAreaView edges={['top']} style={styles.topBar}>
        <Pressable testID="friends-back" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>{owner.is_me ? 'Your friends' : `${firstName}'s friends`}</Text>
          <Text style={styles.subtitle}>
            {friends.length} friend{friends.length === 1 ? '' : 's'}
            {!owner.is_me && mutualCount > 0
              ? ` · ${mutualCount} mutual with you`
              : ''}
          </Text>
        </View>
      </SafeAreaView>

      <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
        {friends.length === 0 ? (
          <View style={styles.emptyBox}>
            <Ionicons name="people-outline" size={26} color={colors.muted} />
            <Text style={styles.emptyText}>No friends yet — follow golfers who follow you back.</Text>
          </View>
        ) : (
          friends.map((f) => (
            <Pressable
              key={f.id}
              testID={`friend-row-${f.id}`}
              onPress={() => router.push(`/user/${f.id}`)}
              style={styles.row}
            >
              <View style={styles.avatar}>
                {f.avatar ? (
                  <Image source={{ uri: f.avatar }} style={{ width: '100%', height: '100%' }} />
                ) : (
                  <Text style={styles.avatarText}>
                    {(f.display_name || 'G')
                      .split(' ')
                      .map((s: string) => s[0])
                      .slice(0, 2)
                      .join('')
                      .toUpperCase()}
                  </Text>
                )}
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <View style={styles.nameRow}>
                  <Text style={styles.name} numberOfLines={1}>
                    {f.display_name}
                    {f.handicap != null ? (
                      <Text style={styles.hcSuffix}> · {f.handicap} HCP</Text>
                    ) : null}
                  </Text>
                </View>
                <View style={styles.badgeRow}>
                  {f.is_me ? (
                    <View style={[styles.badge, styles.badgeMe]}>
                      <Text style={styles.badgeText}>You</Text>
                    </View>
                  ) : f.is_friend ? (
                    <View style={[styles.badge, styles.badgeMutual]}>
                      <Ionicons name="people" size={11} color="#fff" />
                      <Text style={styles.badgeTextOn}>Mutual friend</Text>
                    </View>
                  ) : f.is_following ? (
                    <View style={[styles.badge, styles.badgeFollowing]}>
                      <Text style={styles.badgeText}>You follow</Text>
                    </View>
                  ) : null}
                  <Text style={styles.roundCount}>
                    {f.round_count} round{f.round_count === 1 ? '' : 's'}
                  </Text>
                </View>
              </View>
              {!f.is_me ? (
                <Pressable
                  testID={`friend-follow-${f.id}`}
                  hitSlop={8}
                  onPress={(e) => {
                    e.stopPropagation();
                    toggleFollow(f.id);
                  }}
                  style={[styles.followBtn, f.is_following ? styles.followBtnOn : styles.followBtnOff]}
                >
                  <Ionicons
                    name={f.is_following ? 'checkmark' : 'add'}
                    size={14}
                    color={f.is_following ? '#fff' : colors.brandDeep}
                  />
                  <Text style={f.is_following ? styles.followBtnTextOn : styles.followBtnTextOff}>
                    {f.is_following ? 'Following' : 'Follow'}
                  </Text>
                </Pressable>
              ) : null}
            </Pressable>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
  },
  iconBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  title: { fontSize: 20, fontWeight: '800', color: colors.onSurface },
  subtitle: { fontSize: 13, color: colors.muted, marginTop: 2 },
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: 60 },
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
    width: 48,
    height: 48,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarText: { color: colors.onBrandTertiary, fontWeight: '800', fontSize: 15 },
  nameRow: { flexDirection: 'row', alignItems: 'center' },
  name: { fontSize: 15, fontWeight: '800', color: colors.onSurface, flexShrink: 1 },
  hcSuffix: { color: colors.muted, fontWeight: '600' },
  badgeRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceTertiary,
  },
  badgeMutual: { backgroundColor: colors.brandDeep },
  badgeFollowing: { backgroundColor: colors.brandTertiary },
  badgeMe: { backgroundColor: colors.surfaceInverse },
  badgeText: { fontSize: 10, fontWeight: '800', color: colors.onSurfaceTertiary, letterSpacing: 0.3 },
  badgeTextOn: { fontSize: 10, fontWeight: '800', color: '#fff', letterSpacing: 0.3 },
  roundCount: { fontSize: 11, color: colors.muted, fontWeight: '700' },
  followBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1.5,
  },
  followBtnOff: { backgroundColor: '#fff', borderColor: colors.brandDeep },
  followBtnOn: { backgroundColor: colors.brandDeep, borderColor: colors.brandDeep },
  followBtnTextOff: { color: colors.brandDeep, fontSize: 12, fontWeight: '800' },
  followBtnTextOn: { color: '#fff', fontSize: 12, fontWeight: '800' },
  emptyBox: {
    padding: spacing.xxl,
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    ...shadow.soft,
  },
  emptyText: { fontSize: 13, color: colors.muted, textAlign: 'center', maxWidth: 260 },
});
