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
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { colors, radius, shadow, spacing } from '@/src/theme';
import { makeThemedSheet } from '@/src/theme';
import { useTheme } from '@/src/theme-context';
import { api } from '@/src/api';

type Notification = {
  id: string;
  type: string;
  title: string;
  body: string;
  read: boolean;
  created_at: string;
  course_name?: string;
  reason?: string;
  round_id?: string;
  comment_id?: string;
  actor_id?: string;
  actor_name?: string;
  achievement_key?: string;
};

function iconForType(type: string): { icon: any; color: string } {
  switch (type) {
    case 'achievement_unlocked':
      return { icon: 'trophy', color: colors.brandPrimary };
    case 'comment_like':
      return { icon: 'heart', color: colors.brandSecondary };
    case 'post_like':
      return { icon: 'heart', color: colors.brandSecondary };
    case 'post_comment':
      return { icon: 'chatbubble', color: colors.brandPrimary };
    case 'mention':
      return { icon: 'at', color: colors.brandPrimary };
    case 'follow':
      return { icon: 'person-add', color: colors.brandPrimary };
    case 'course_rejected':
      return { icon: 'alert-circle', color: '#c0392b' };
    case 'course_verified':
      return { icon: 'checkmark-done', color: colors.brandPrimary };
    case 'lfg_interest':
      return { icon: 'hand-right', color: colors.brandPrimary };
    case 'lfg_response':
      return { icon: 'people', color: colors.brandPrimary };
    default:
      return { icon: 'notifications', color: colors.brandPrimary };
  }
}

/** Where tapping a notification should take the user, based on its type. */
function resolveNotificationTarget(n: Notification): string | null {
  switch (n.type) {
    case 'post_like':
    case 'post_comment':
    case 'comment_like':
    case 'mention':
    case 'achievement_unlocked':
    case 'lfg_interest':
    case 'lfg_response':
      // Achievements are earned by a specific round, so jump straight to it.
      return n.round_id ? `/post/${n.round_id}` : null;
    case 'follow':
      return n.actor_id ? `/user/${n.actor_id}` : null;
    case 'course_verified':
      return n.course_name ? `/course/${encodeURIComponent(n.course_name)}` : null;
    default:
      // e.g. course_rejected — the course record no longer exists to open.
      return null;
  }
}

export default function NotificationsScreen() {
  useTheme();
  const router = useRouter();
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const load = useCallback(async () => {
    try {
      const res = await api.listNotifications();
      setItems(res.notifications);
    } catch {
      // Silent — if it fails just show empty
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Mark everything as read as soon as the user opens the screen.
  useEffect(() => {
    if (items.some((n) => !n.read)) {
      api.markAllNotificationsRead().catch(() => {});
    }
  }, [items]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const onPressNotification = (n: Notification) => {
    Haptics.selectionAsync().catch(() => {});
    if (!n.read) {
      setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
      api.markNotificationRead(n.id).catch(() => {});
    }
    const target = resolveNotificationTarget(n);
    if (target) router.push(target as any);
  };

  return (
    <SafeAreaView edges={['top']} style={styles.container}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} hitSlop={8} testID="notif-back">
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Notifications</Text>
        <View style={{ width: 40 }} />
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.brandPrimary} size="large" />
        </View>
      ) : items.length === 0 ? (
        <View style={styles.center}>
          <View style={styles.emptyIcon}>
            <Ionicons name="notifications-off-outline" size={32} color={colors.muted} />
          </View>
          <Text style={styles.emptyTitle}>You&apos;re all caught up</Text>
          <Text style={styles.emptySub}>We&apos;ll let you know if something needs your attention.</Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
        >
          {items.map((n) => {
            const meta = iconForType(n.type);
            const target = resolveNotificationTarget(n);
            return (
              <Pressable
                key={n.id}
                testID={`notif-${n.id}`}
                onPress={() => onPressNotification(n)}
                disabled={!target}
                style={[styles.card, !n.read && styles.cardUnread]}
              >
                <View style={styles.iconWrap}>
                  <Ionicons name={meta.icon} size={22} color={meta.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle}>{n.title}</Text>
                  <Text style={styles.cardBody}>{n.body}</Text>
                  <Text style={styles.cardTime}>{new Date(n.created_at).toLocaleDateString()}</Text>
                </View>
                {!n.read ? <View style={styles.unreadDot} /> : null}
                {target ? (
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} style={{ marginLeft: 2, alignSelf: 'center' }} />
                ) : null}
              </Pressable>
            );
          })}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = makeThemedSheet((colors: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  backBtn: { width: 40, height: 40, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { flex: 1, fontSize: 18, fontWeight: '800', color: colors.onSurface, textAlign: 'center' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.md },
  emptyIcon: {
    width: 72,
    height: 72,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: colors.onSurface },
  emptySub: { fontSize: 14, color: colors.muted, textAlign: 'center', maxWidth: 260 },
  card: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    marginBottom: spacing.sm,
    ...shadow.soft,
  },
  cardUnread: { backgroundColor: colors.brandTertiary },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardTitle: { fontSize: 14, fontWeight: '800', color: colors.onSurface },
  cardBody: { fontSize: 13, color: colors.onSurface, marginTop: 2, lineHeight: 18 },
  cardTime: { fontSize: 11, color: colors.muted, marginTop: 6, fontWeight: '600' },
  unreadDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.brandPrimary,
    marginTop: 6,
  },
}));
