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
    default:
      return { icon: 'notifications', color: colors.brandPrimary };
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
            return (
              <View key={n.id} style={[styles.card, !n.read && styles.cardUnread]} testID={`notif-${n.id}`}>
                <View style={styles.iconWrap}>
                  <Ionicons name={meta.icon} size={22} color={meta.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle}>{n.title}</Text>
                  <Text style={styles.cardBody}>{n.body}</Text>
                  <Text style={styles.cardTime}>{new Date(n.created_at).toLocaleDateString()}</Text>
                </View>
                {!n.read ? <View style={styles.unreadDot} /> : null}
              </View>
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
